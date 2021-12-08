# Lynette Davis
# Center for Coastal and Ocean Mapping
# University of New Hampshire
# April 2021

# Description:
# See https://stackoverflow.com/questions/11874767/how-do-i-plot-in-real-time-in-a-while-loop-using-matplotlib for
# adding updating plot to GUI.

import ctypes
import datetime
from KmallReaderForMDatagrams import KmallReaderForMDatagrams as k
from KongsbergDGPie import KongsbergDGPie
import logging
import math
from multiprocessing import Process, shared_memory, Value
import numpy as np
#from numpy_ringbuffer import RingBuffer
from NumpyRingBuffer import NumpyRingBuffer
import pyqtgraph as pg
# import pyvista as pv  # "Easier Pythonic interface to VTK"
# from pyvistaqt import BackgroundPlotter, QtInteractor
from PyQt5.QtCore import QTimer
import sched
import statistics
from GUI.SubwindowHorizontalSliceWidget import SubwindowHorizontalSliceWidget
import threading
import time
import queue
import warnings

logger = logging.getLogger(__name__)

class Plotter2(Process):
    def __init__(self, settings, queue_pie_object, queue_plot, queue_lat_lon, queue_timestamp,
                 raw_buffer_indices=None, processed_buffer_indices=None, process_boolean=None):
        super().__init__()

        print("New instance of Plotter.")

        self.settings = settings

        # multiprocessing.Queues
        self.queue_pie_object = queue_pie_object
        self.queue_plot = queue_plot
        self.queue_lat_lon = queue_lat_lon
        self.queue_timestamp = queue_timestamp

        # multiprocessing.Arrays
        self.raw_buffer_indices = raw_buffer_indices
        self.processed_buffer_indices = processed_buffer_indices

        # Boolean shared across processes (multiprocessing.Value)
        if process_boolean:
            self.process_boolean = process_boolean
        else:
            self.process_boolean = Value(ctypes.c_bool, True)

        self.MAX_NUM_GRID_CELLS = self.settings['buffer_settings']['maxGridCells']
        self.MAX_LENGTH_BUFFER = self.settings['buffer_settings']['maxBufferSize']

        # TODO: Shared memory experiment:
        # https://medium.com/@sampsa.riikonen/doing-python-multiprocessing-the-right-way-a54c1880e300
        # https://github.com/elsampsa/medium/blob/main/multiprocess/example2.py
        self.name = "PlotterProcess"

        # Create shared memory in the frontend: note create=False
        self.shmem_amplitude_buffer = None
        self.shmem_count_buffer = None
        self.shmem_timestamp_buffer = None
        self.shmem_lat_lon_buffer = None

        self.shmem_vertical_slice_buffer = None
        self.shmem_horizontal_slice_buffer = None
        self.shmem_timestamp_buffer_avg = None
        self.shmem_lat_lon_buffer_avg = None

        # Create numpy arrays from the shared memory
        self.amplitude_buffer = None
        self.count_buffer = None
        self.timestamp_buffer = None
        self.lat_lon_buffer = None

        self.vertical_slice_buffer = None
        self.horizontal_slice_buffer = None
        self.timestamp_buffer_avg = None
        self.lat_lon_buffer_avg = None

        # TODO: Add constants to setting dictionary?
        self.QUEUE_RX_TIMEOUT = 60  # Seconds

        self.PIE_VMIN = -95
        self.PIE_VMAX = 10
        self.PLOT_UPDATE_INTERVAL = 1000  # Milliseconds

        # VERTICAL SLICE:
        # Trim arrays to omit values outside of self.vertical_slice_width_m
        # start_index       end_index
        #          |X|_|_|_|X|
        #          |X|_|_|_|X|
        #          |X|_|_|_|X|
        #          |X|_|_|_|X|

        self.vertical_slice_start_index = None
        self.vertical_slice_end_index = None
        self.set_vertical_indices()

        # HORIZONTAL SLICE:
        # Trim arrays to omit values outside of self.horizontal_slice_width_m
        # |X|X|X|X|X| start_index
        # |_|_|_|_|_|
        # |_|_|_|_|_|
        # |X|X|X|X|X| end_index
        self.horizontal_slice_start_index = None
        self.horizontal_slice_end_index = None
        self.set_horizontal_indices()

        # ! ! ! ! ! ! ! ! ! ! ! ! ! ! ! ! ! ! ! ! ! ! ! ! ! ! ! ! ! ! ! ! ! ! ! ! ! ! ! !

        self.collapse_times = []  # For testing
        self.test_x = [0.1, 0.2, 0.3, 0.4, 5, 6, 7, 8, 9, 10]
        self.test_y = [3, 3, 3, 32, 33, 31, 29, 32, 35, 45]

    def printhi(self):
        print("hi")

    def set_vertical_indices(self):
        # TODO: Double check that this is calculated correctly
        self.vertical_slice_start_index = math.floor((self.MAX_NUM_GRID_CELLS / 2) -
                                                     ((self.settings["processing_settings"]["acrossTrackAvg_m"] / 2) /
                                                      self.settings["processing_settings"]["binSize_m"]))
        self.vertical_slice_end_index = math.ceil((self.MAX_NUM_GRID_CELLS / 2) +
                                                  ((self.settings["processing_settings"]["acrossTrackAvg_m"] / 2) /
                                                   self.settings["processing_settings"]["binSize_m"]))
    def set_horizontal_indices(self):
        # TODO: Double check that this is calculated correctly
        # First, find index of zero depth: this is found by dividing max_heave by bin_size
        # Then, find index of desired depth of slice: this is found by dividing horizontal_slice_depth_m by bin_size
        # Add the above two values to get true index of desired depth.
        # Then, find number of bins that must be included to achieve horizontal_slice_width_m above / below index of
        # desired depth: this is found by dividing horizontal_slice_width_m by 2 and dividing again by bin_size.
        self.horizontal_slice_start_index = math.ceil(self.settings["buffer_settings"]["maxHeave_m"] /
                                                      self.settings["processing_settings"]["binSize_m"]) + \
                                            math.floor(self.settings["processing_settings"]["depth_m"] /
                                                       self.settings["processing_settings"]["binSize_m"]) - \
                                            math.ceil((self.settings["processing_settings"]["depthAvg_m"] / 2) /
                                                      self.settings["processing_settings"]["binSize_m"])
        self.horizontal_slice_end_index = math.ceil(self.settings["buffer_settings"]["maxHeave_m"] /
                                                    self.settings["processing_settings"]["binSize_m"]) + \
                                          math.floor(self.settings["processing_settings"]["depth_m"] /
                                                     self.settings["processing_settings"]["binSize_m"]) + \
                                          math.ceil((self.settings["processing_settings"]["depthAvg_m"] / 2) /
                                                    self.settings["processing_settings"]["binSize_m"])

    def get_and_plot_pie(self):
        print("DGPlot: get_and_plot_pie")  # For debugging
        self.start_time = datetime.datetime.now()

        threading.Thread(target=self.get_and_buffer_pie, daemon=True).start()

        # print("qtimer start")
        # timer = QTimer()
        # timer.timeout.connect(self.update)
        # timer.start(self.PLOT_UPDATE_INTERVAL)
        # print("qtimer end")

        # self.animation = anim.FuncAnimation(self.fig, self.__animate, fargs=(),
        #                                     interval=self.PLOT_UPDATE_INTERVAL)

        #plt.show(block=True)
        pass

    def retrieve_plot_matrices(self):
        # For testing:
        # self.plot_count += 1
        # print("Plot count: ", self.plot_count)
        # print("Animate timestamp: ", datetime.datetime.now())

        pie_display = []
        #self._lock_raw_buffers.acquire()
        try:
            with np.errstate(divide='ignore', invalid='ignore'):
                # Quick method of averaging!
                # TODO: This will give the most recent 'pie' in the buffer with no averaging--is that what we want?
                pie_display = np.array(self.pie_values_buffer.peek() / self.pie_count_buffer.peek())
        except IndexError:
            logger.warning("Excepted IndexError in retrieving values from buffer.")
        finally:
            #self._lock_raw_buffers.release()
            pass

        vertical_slice = []
        horizontal_slice = []
        timestamp_slice = []
        lat_lon_slice = []

        # For testing:
        start = datetime.datetime.now()

        #self._lock_slice_buffers.acquire()  # NOTE: Time to acquire this lock is pretty much always zero (0019 test file).

        try:  # NOTE: Time to copy these data structures is pretty much always zero (0019 test file).
            # TODO: This will make a new temporary object--is that what we want? Is it necessary?
            # vertical_slice = np.array(self.vertical_slice_buffer).astype(np.float32)
            vertical_slice = np.array(self.vertical_slice_buffer).__array__(np.float32)
            horizontal_slice = np.array(self.horizontal_slice_buffer).__array__(np.float32)
            timestamp_slice = np.array(self.timestamp_slice_buffer)
            lat_lon_slice = np.array(self.lat_lon_slice_buffer)
        finally:
            #self._lock_slice_buffers.release()
            pass

        # For testing:
        end = datetime.datetime.now()
        diff = (end - start).total_seconds()
        print("Time to copy data structures: ", diff)  # This always appears to be zero.

        if np.any(vertical_slice) and np.any(horizontal_slice):
            # For testing:
            print("len(vertical_slice) at animate update: ", len(vertical_slice))

            # Trim NaNs from matrices to be plotted:
            # This method will look for the index of the last row that is not completely filled with NaNs.
            # Add one to that index for the first full row of NaNs after all data.
            index_pie_display = np.argwhere(~np.isnan(pie_display).all(axis=1))[-1][0] + 1
            index_vertical_slice = np.argwhere(~np.isnan(vertical_slice).all(axis=0))[-1][0] + 1
            # TODO:
            # Minus one to find first full row of NaNs before data.

            # index_horizontal_slice_a = np.argwhere(~np.isnan(horizontal_slice).all(axis=0))[0][0] - 1
            # index_horizontal_slice_b = np.argwhere(~np.isnan(horizontal_slice).all(axis=0))[-1][0] + 1

            # Ensure that 'index' plus some small buffer does not exceed grid size.
            # (Because we want to allow some small buffer around bottom of data if possible.)
            index_pie_display = min((index_pie_display + 10), self.MAX_NUM_GRID_CELLS)
            index_vertical_slice = min((index_vertical_slice + 10), self.MAX_NUM_GRID_CELLS)
            # TODO:
            # index_horizontal_slice_a = max((index_horizontal_slice_a - 10), 0)
            # index_horizontal_slice_b = min((index_horizontal_slice_b + 10), self.MAX_NUM_GRID_CELLS)

            print("****************verticalslice.shape: ", vertical_slice[:index_vertical_slice, :].shape)
            print("len(verticalslice): ", len(vertical_slice[:index_vertical_slice, :]))

            return pie_display[:][:index_pie_display].T, \
                   vertical_slice[:index_vertical_slice, :], horizontal_slice
                   # horizontal_slice[index_horizontal_slice_a:index_horizontal_slice_b, :]

            # # Update plots:
            # self.ax_pie.clear()
            # self.ax_vert.clear()
            # self.ax_horiz.clear()
            # print("*****PLOTTING*****")
            # self.ax_pie.imshow(pie_display[:][:index_pie_display], cmap='gray',
            #                    vmin=self.PIE_VMIN, vmax=self.PIE_VMAX)  # Greyscale
            # # TODO: NOTE: matplotlib gives "unsupported dtype" error with np.float16; use np.float32.
            # # self.ax_vert.imshow(vertical_slice, cmap='gray',
            # #                     vmin=self.PIE_VMIN, vmax=self.PIE_VMAX)  # Greyscale
            # self.ax_vert.imshow(vertical_slice.T[:index_vertical_slice, :], cmap='gray',
            #                     vmin=self.PIE_VMIN, vmax=self.PIE_VMAX)  # Greyscale
            # self.ax_horiz.imshow(horizontal_slice.T[index_horizontal_slice_a:index_horizontal_slice_b, :], cmap='gray',
            #                      vmin=self.PIE_VMIN, vmax=self.PIE_VMAX)  # Greyscale
            # plt.draw()
            # plt.pause(0.001)

        else:
            logger.warning("Nothing to plot; water column data matrix buffer is empty.")

    def get_sliced_matrices(self):
        pass

    def get_pie_matrix(self):
        with self.raw_buffer_indices.get_lock():
            temp_pie_amplitude = self.amplitude_buffer[(self.raw_buffer_indices[0] % self.MAX_LENGTH_BUFFER) - 1]
            temp_pie_count = self.count_buffer[(self.raw_buffer_indices[0] % self.MAX_LENGTH_BUFFER) - 1]
            return temp_pie_amplitude / temp_pie_count

    def get_vertical_slice(self):
        pass

    def get_horizontal_slice(self):
        pass

    def get_and_buffer_pie(self):
        # TODO: This could possibly be moved to KongsbergDGProcess???
        #  Or is this best for compatibility with other systems?
        print("DGPlot: get_and_buffer_pie")  # For debugging

        raw_buffer_pointer = 0

        start_rx_time = 0
        test_count = 0

        count_total = 0
        count_temp = 0

        temp_pie_values = []
        temp_pie_count = []
        temp_timestamp = []
        temp_lat_lon = []

        #while True:
        while self.process_boolean.value:
            try:
                pie_object = self.queue_pie_object.get(block=True, timeout=self.QUEUE_RX_TIMEOUT)

                with self.raw_buffer_indices.get_lock():
                    if self.len_buffer() == self.MAX_LENGTH_BUFFER:  # Buffer is full
                        #Increment 'left' index
                        self.raw_buffer_indices[0] = self.raw_buffer_indices[0] + 1
                        # self.raw_buffer_indices[0] = self.raw_buffer_indices[0] + \
                        #                               self.settings['processing_settings']['alongTrackAvg_ping']

                    # Add values to buffers:
                    self.amplitude_buffer[self.raw_buffer_indices[1] % self.MAX_LENGTH_BUFFER] = pie_object.pie_chart_values
                    self.count_buffer[self.raw_buffer_indices[1] % self.MAX_LENGTH_BUFFER] = pie_object.pie_chart_count
                    self.timestamp_buffer[self.raw_buffer_indices[1] % self.MAX_LENGTH_BUFFER] = pie_object.timestamp
                    self.lat_lon_buffer[self.raw_buffer_indices[1] % self.MAX_LENGTH_BUFFER] = (pie_object.latitude, pie_object.longitude)

                    # Increment 'right' index:
                    self.raw_buffer_indices[1] = self.raw_buffer_indices[1] + 1
                    self._fix_indices()

                    print("Length of buffer!: ", self.len_buffer())

                    count_temp += 1

                    if self.len_buffer() % self.settings["processing_settings"]["alongTrackAvg_ping"] == 0 \
                            and self.len_buffer() > 0:
                        # TODO: Need to implement some kind of 'unwrap' function here for wrapped arrays:

                        temp_pie_values = np.copy(self.amplitude_buffer[(self.raw_buffer_indices[1] -
                                                                self.settings['processing_settings']
                                                                ['alongTrackAvg_ping']
                                                                 - 1):(self.raw_buffer_indices[1] - 1)])

                        temp_pie_count = np.copy(self.count_buffer[(self.raw_buffer_indices[1] -
                                                                self.settings['processing_settings']
                                                                ['alongTrackAvg_ping']
                                                                - 1):(self.raw_buffer_indices[1] - 1)])

                        temp_timestamp = np.copy(self.timestamp_buffer[(self.raw_buffer_indices[1] -
                                                                self.settings['processing_settings']
                                                                ['alongTrackAvg_ping']
                                                                - 1):(self.raw_buffer_indices[1] - 1)])

                        temp_lat_lon = np.copy(self.lat_lon_buffer[(self.raw_buffer_indices[1] -
                                                            self.settings['processing_settings']['alongTrackAvg_ping']
                                                            - 1):(self.raw_buffer_indices[1] - 1)])

                        print("len(temp_pie_values):", len(temp_pie_values))

                # Release lock

                if self.len_buffer() % self.settings["processing_settings"]["alongTrackAvg_ping"] == 0 \
                        and self.len_buffer() > 0:

                    # vertical_slice_average, horizontal_slice_average, timestamp_average, lat_lon_average = \
                    #     self.collapse_and_buffer_pings(temp_pie_values, temp_pie_count, temp_timestamp, temp_lat_lon)

                    self.collapse_and_buffer_pings(temp_pie_values, temp_pie_count, temp_timestamp, temp_lat_lon)



                #     count = 0
                #
                #     #self._lock_slice_buffers.acquire()
                #     try:
                #         print("Appending to slice buffers")
                #         self.vertical_slice_buffer.append(vertical_slice_average)
                #         self.horizontal_slice_buffer.append(horizontal_slice_average)
                #         self.timestamp_slice_buffer.append(timestamp_average)
                #         self.lat_lon_slice_buffer.append(timestamp_average)
                #     finally:
                #         #self._lock_slice_buffers.release()
                #         pass
                #
                #     print("self.vertical_slice_buffer.shape:", self.vertical_slice_buffer.shape)

            except queue.Empty:
                # TODO: Shutdown processes when queue is empty?
                logger.exception("Datagram queue empty exception.")
                break

            # print("buffering pie")
            # self.pie_values_buffer.append(pie_object.pie_chart_values)
            # self.pie_count_buffer.append(pie_object.pie_chart_count)
            # self.timestamp_buffer.append(pie_object.timestamp)
            # self.lat_lon_buffer.append([pie_object.latitude, pie_object.longitude])

            # if self.queue_pie_object.qsize() == 0:  # For testing
            #     end_rx_time = datetime.datetime.now()
            #     diff = (end_rx_time - start_rx_time).total_seconds()
            # print("DGPLOT, time to deque {} MWC plots: {}".format(test_count, diff))

        # print("TIME TO DEQUE ALL ITEMS IN QUEUE: {}".format(self.start_time - datetime.datetime.now()))
        self.closeSharedMemory()


    # def get_and_buffer_pie(self):
    #     # TODO: This could possibly be moved to KongsbergDGProcess???
    #     #  Or is this best for compatibility with other systems?
    #     print("DGPlot: get_and_buffer_pie")  # For debugging
    #
    #     raw_buffer_pointer = 0
    #
    #     start_rx_time = 0
    #     test_count = 0
    #
    #     count = 0
    #
    #     temp_pie_values = []
    #     temp_pie_count = []
    #     temp_timestamp = []
    #     temp_lat_lon = []
    #
    #     #while True:
    #     while self.process_boolean.value:
    #         try:
    #             pie_object = self.queue_pie_object.get(block=True, timeout=self.QUEUE_RX_TIMEOUT)
    #             count += 1
    #
    #             # if test_count == 0:  # For testing
    #             #     start_rx_time = datetime.datetime.now()
    #             # test_count += 1
    #             print("count: ", count)
    #
    #                 if (self.raw_buffer_indices[1] - self.raw_buffer_indices[0]) == self.MAX_LENGTH_BUFFER:
    #                     # Buffer is full
    #                     if self.MAX_LENGTH_BUFFER == 0:
    #                         # Cannot add to buffer of max length zero
    #                         raise IndexError("Cannot append to array with maximum length zero.")
    #                     else:
    #                         # Increment 'left' index
    #                         self.raw_buffer_indices[0] = self.raw_buffer_indices[0] + 1
    #                         # self.raw_buffer_indices[0] = self.raw_buffer_indices[0] + \
    #                         #                               self.settings['processing_settings']['alongTrackAvg_ping']
    #
    #                 #print("get and buffer pie: ", np.nonzero(pie_object.pie_chart_count))
    #                 # Add values to buffers:
    #                 self.amplitude_buffer[self.raw_buffer_indices[1] % self.MAX_LENGTH_BUFFER] = pie_object.pie_chart_values
    #                 self.count_buffer[self.raw_buffer_indices[1] % self.MAX_LENGTH_BUFFER] = pie_object.pie_chart_count
    #                 self.timestamp_buffer[self.raw_buffer_indices[1] % self.MAX_LENGTH_BUFFER] = pie_object.timestamp
    #                 self.lat_lon_buffer[self.raw_buffer_indices[1] % self.MAX_LENGTH_BUFFER] = (pie_object.latitude, pie_object.longitude)
    #
    #                 # Increment 'right' index:
    #                 self.raw_buffer_indices[1] = self.raw_buffer_indices[1] + 1
    #                 self._fix_indices()
    #
    #             print("Length of buffer!: ", self.len_buffer())
    #
    #
    #             # if count == self.settings["processing_settings"]["alongTrackAvg_ping"]:
    #             #     temp_pie_values = np.array(self.pie_values_buffer[-self.settings["processing_settings"]["alongTrackAvg_ping"]:])
    #             #     temp_pie_count = np.array(self.pie_count_buffer[-self.settings["processing_settings"]["alongTrackAvg_ping"]:])
    #             #     temp_timestamp = np.array(self.timestamp_buffer[-self.settings["processing_settings"]["alongTrackAvg_ping"]:])
    #             #     temp_lat_lon = np.array(self.lat_lon_buffer[-self.settings["processing_settings"]["alongTrackAvg_ping"]:])
    #             # TODO: Catch exceptions here?
    #             # finally:
    #             #     #self._lock_raw_buffers.release()
    #             #     pass
    #
    #             # if count == self.settings["processing_settings"]["alongTrackAvg_ping"]:
    #             #     vertical_slice_average, horizontal_slice_average, timestamp_average, lat_lon_average = \
    #             #         self.collapse_and_buffer_pings(temp_pie_values, temp_pie_count, temp_timestamp, temp_lat_lon)
    #             #     count = 0
    #             #
    #             #     #self._lock_slice_buffers.acquire()
    #             #     try:
    #             #         print("Appending to slice buffers")
    #             #         self.vertical_slice_buffer.append(vertical_slice_average)
    #             #         self.horizontal_slice_buffer.append(horizontal_slice_average)
    #             #         self.timestamp_slice_buffer.append(timestamp_average)
    #             #         self.lat_lon_slice_buffer.append(timestamp_average)
    #             #     finally:
    #             #         #self._lock_slice_buffers.release()
    #             #         pass
    #             #
    #             #     print("self.vertical_slice_buffer.shape:", self.vertical_slice_buffer.shape)
    #
    #         except queue.Empty:
    #             # TODO: Shutdown processes when queue is empty?
    #             logger.exception("Datagram queue empty exception.")
    #             break
    #
    #         # print("buffering pie")
    #         # self.pie_values_buffer.append(pie_object.pie_chart_values)
    #         # self.pie_count_buffer.append(pie_object.pie_chart_count)
    #         # self.timestamp_buffer.append(pie_object.timestamp)
    #         # self.lat_lon_buffer.append([pie_object.latitude, pie_object.longitude])
    #
    #         # if self.queue_pie_object.qsize() == 0:  # For testing
    #         #     end_rx_time = datetime.datetime.now()
    #         #     diff = (end_rx_time - start_rx_time).total_seconds()
    #             # print("DGPLOT, time to deque {} MWC plots: {}".format(test_count, diff))
    #
    #     # print("TIME TO DEQUE ALL ITEMS IN QUEUE: {}".format(self.start_time - datetime.datetime.now()))
    #     self.closeSharedMemory()

    def collapse_and_buffer_pings(self, temp_pie_values, temp_pie_count, temp_timestamp, temp_lat_lon):
        # For testing:
        start = datetime.datetime.now()
        print("collapse_and_buffer timestamp: ", start)

        # pie_values_vertical_average = []
        # pie_values_horizontal_average = []
        # pie_timestamp_average = []
        # pie_lat_lon_average = []

        if np.any(temp_pie_values) and np.any(temp_pie_count):
            print("Collapse buffer")

            # VERTICAL SLICE:
            # Trim arrays to omit values outside of self.vertical_slice_width_m
            # start_index       end_index
            #          |X|_|_|_|X|
            #          |X|_|_|_|X|
            #          |X|_|_|_|X|
            #          |X|_|_|_|X|
            pie_values_vertical = temp_pie_values[:, :, self.vertical_slice_start_index:self.vertical_slice_end_index]
            pie_count_vertical = temp_pie_count[:, :, self.vertical_slice_start_index:self.vertical_slice_end_index]

            # "Collapse" arrays by adding every self.num_pings_to_average so that
            # len(_collapsed_array_) = len(_array_) / self.num_pings_to_average = 1
            pie_values_vertical = np.sum(pie_values_vertical, axis=0)
            pie_count_vertical = np.sum(pie_count_vertical, axis=0)

            # Sum rows of matrices:
            pie_values_vertical = np.sum(pie_values_vertical, axis=1)
            pie_count_vertical = np.sum(pie_count_vertical, axis=1)
            # print("pie_values.shape after sum rows:", pie_values_vertical.shape)
            # print("pie_count.shape after sum rows:", pie_count_vertical.shape)

            # Ignore divide by zero warnings. Division by zero results in NaN, which is what we want.
            with np.errstate(divide='ignore', invalid='ignore'):
                pie_values_vertical_average = pie_values_vertical / pie_count_vertical

            print("pie_values_vertical_average.shape: ", pie_values_vertical_average.shape)

            # HORIZONTAL SLICE:
            # Trim arrays to omit values outside of self.horizontal_slice_width_m
            # |X|X|X|X|X| start_index
            # |_|_|_|_|_|
            # |_|_|_|_|_|
            # |X|X|X|X|X| end_index
            pie_values_horizontal = temp_pie_values[:, self.horizontal_slice_start_index:
                                                       self.horizontal_slice_end_index, :]
            pie_count_horizontal = temp_pie_count[:, self.horizontal_slice_start_index:
                                                     self.horizontal_slice_end_index, :]

            # "Collapse" arrays by adding every self.num_pings_to_average so that
            # len(_collapsed_array_) = len(_array_) / self.num_pings_to_average = 1
            pie_values_horizontal = np.sum(pie_values_horizontal, axis=0)
            pie_count_horizontal = np.sum(pie_count_horizontal, axis=0)

            # Sum columns of matrices:
            pie_values_horizontal = np.sum(pie_values_horizontal, axis=0)
            pie_count_horizontal = np.sum(pie_count_horizontal, axis=0)
            # print("pie_values.shape after sum rows:", pie_values_vertical.shape)
            # print("pie_count.shape after sum rows:", pie_count_vertical.shape)

            # Ignore divide by zero warnings. Division by zero results in NaN, which is what we want.
            with np.errstate(divide='ignore', invalid='ignore'):
                pie_values_horizontal_average = pie_values_horizontal / pie_count_horizontal
        else:
            logger.warning("Water column data matrix buffers are empty.")
            pie_values_vertical_average = pie_values_horizontal_average = \
                np.empty((self.MAX_NUM_GRID_CELLS))
            pie_values_vertical_average[:] = np.nan

        pie_timestamp_average = []
        if np.any(temp_timestamp):
            # "Collapse" arrays by adding every self.num_pings_to_average so that
            # len(_collapsed_array_) = len(_array_) / self.num_pings_to_average
            pie_timestamp = np.sum(temp_timestamp)
            # Ignore divide by zero warnings. Division by zero results in NaN, which is what we want.
            with np.errstate(divide='ignore', invalid='ignore'):
                pie_timestamp_average = pie_timestamp / self.settings["processing_settings"]["alongTrackAvg_ping"]
        else:
            logger.warning("Water column timestamp matrix buffer is empty.")
            pie_timestamp_average = np.empty(1)
            pie_timestamp_average[:] = np.nan

        pie_lat_lon_average = []
        if np.any(temp_lat_lon):
            # "Collapse" arrays by adding every self.num_pings_to_average so that
            # len(_collapsed_array_) = len(_array_) / self.num_pings_to_average
            pie_lat_lon = np.sum(temp_lat_lon, axis=0)
            # Ignore divide by zero warnings. Division by zero results in NaN, which is what we want.
            with np.errstate(divide='ignore', invalid='ignore'):
                pie_lat_lon_average = pie_lat_lon / self.settings["processing_settings"]["alongTrackAvg_ping"]
        else:
            logger.warning("Nothing to plot; water column latitude / longitude matrix buffer is empty.")
            pie_lat_lon_average = np.empty(2)
            pie_lat_lon_average[:] = np.nan

        # For testing:
        # end = datetime.datetime.now()
        # diff = (end - start).total_seconds()
        # self.collapse_times.append(diff)
        # print("Time for single collapse: ", diff)
        # print("Min collapse time: ", min(self.collapse_times))
        # print("Max collapse time: ", max(self.collapse_times))
        # print("Average collapse time: ", sum(self.collapse_times) / len(self.collapse_times))

        with self.processed_buffer_indices.get_lock():
            self.vertical_slice_buffer[self.processed_buffer_indices[1] % len(self.vertical_slice_buffer)] = pie_values_vertical_average
            self.horizontal_slice_buffer[self.processed_buffer_indices[1] % len(self.horizontal_slice_buffer)] = pie_values_horizontal_average
            self.timestamp_buffer_avg[self.processed_buffer_indices[1] % len(self.horizontal_slice_buffer)] = pie_timestamp_average
            self.lat_lon_buffer_avg[self.processed_buffer_indices[1] % len(self.horizontal_slice_buffer)] = pie_lat_lon_average

            self.processed_buffer_indices[1] += 1
        #return pie_values_vertical_average, pie_values_horizontal_average, pie_timestamp_average, pie_lat_lon_average

    # def _append(self, buffer, value):
    #     with self.raw_buffer_indices.get_lock():
    #         if (self.raw_buffer_indices[1] - self.raw_buffer_indices[0]) == self.MAX_LENGTH_BUFFER:  # Buffer is full
    #             if (self.raw_buffer_indices[1] - self.raw_buffer_indices[0]) == 0:  # Buffer has zero capacity
    #                 return
    #             else:
    #                 # Increment 'left' index
    #                 self.raw_buffer_indices[0] = self.raw_buffer_indices[0] + 1
    #
    #         buffer[self.raw_buffer_indices[1] % self.capacity] = value
    #         # Increment 'right' index
    #         self.raw_buffer_indices[1] = self.raw_buffer_indices[1] + 1
    #         self._fix_indices()

    def len_buffer(self):
        with self.raw_buffer_indices.get_lock():
            len = self.raw_buffer_indices[1] - self.raw_buffer_indices[0]
        return len

    def _fix_indices(self):
        """
        Enforce our invariant that 0 <= self.raw_buffer_indices[0] < self.MAX_LENGTH_BUFFER
        """
        with self.raw_buffer_indices.get_lock():
            if self.raw_buffer_indices[0] >= self.MAX_LENGTH_BUFFER:
                self.raw_buffer_indices[0] = self.raw_buffer_indices[0] - self.MAX_LENGTH_BUFFER
                self.raw_buffer_indices[1] = self.raw_buffer_indices[1] - self.MAX_LENGTH_BUFFER
            elif self.raw_buffer_indices[0] < 0:
                self.raw_buffer_indices[0] = self.raw_buffer_indices[0] + self.MAX_LENGTH_BUFFER
                self.raw_buffer_indices[1] = self.raw_buffer_indices[1] + self.MAX_LENGTH_BUFFER

    def closeSharedMemory(self):
        # Quit using shared memory in the backend
        self.shmem_amplitude_buffer.close()
        self.shmem_count_buffer.close()
        self.shmem_timestamp_buffer.close()
        self.shmem_lat_lon_buffer.close()

    # def unlinkSharedMemory(self):
    #     # Release shared memory definitely
    #     self.shmem_amplitude_buffer.unlink()
    #     self.shmem_count_buffer.unlink()
    #     self.shmem_timestamp_buffer.unlink()
    #     self.shmem_lat_lon_buffer.unlink()

    def run(self):
        print("In Plotter.run()")
        amplitude_dtype = np.dtype((np.float16, (self.MAX_NUM_GRID_CELLS, self.MAX_NUM_GRID_CELLS)))
        count_dtype = np.dtype((np.uint16, (self.MAX_NUM_GRID_CELLS, self.MAX_NUM_GRID_CELLS)))
        timestamp_dtype = np.dtype(np.float32)
        lat_lon_dtype = np.dtype((np.float32, 2))
        slice_dtype = np.dtype((np.float16, self.MAX_NUM_GRID_CELLS))
        #
        # total_size = (amplitude_dtype.itemsize + count_dtype.itemsize + timestamp_dtype.itemsize +
        #               lat_lon_dtype.itemsize) * self.MAX_LENGTH_BUFFER
        #
        # print("TOTAL SIZE (bytes): ", total_size)
        # print("TOTAL SIZE (MB): ", total_size / 1024 / 1024)
        #
        # # Create shared memory in the frontend: note create=False
        self.shmem_amplitude_buffer = shared_memory.SharedMemory(name="shmem_amplitude_buffer", create=False,
                                                                 size=(self.MAX_LENGTH_BUFFER * amplitude_dtype.itemsize))
        self.shmem_count_buffer = shared_memory.SharedMemory(name="shmem_count_buffer", create=False,
                                                             size=self.MAX_LENGTH_BUFFER * count_dtype.itemsize)
        self.shmem_timestamp_buffer = shared_memory.SharedMemory(name="shmem_timestamp_buffer", create=False,
                                                                 size=self.MAX_LENGTH_BUFFER * timestamp_dtype.itemsize)
        self.shmem_lat_lon_buffer = shared_memory.SharedMemory(name="shmem_lat_lon_buffer", create=False,
                                                               size=self.MAX_LENGTH_BUFFER * lat_lon_dtype.itemsize)

        self.shmem_vertical_slice_buffer = shared_memory.SharedMemory(name="shmem_vertical_slice_buffer",
                                                                  create=False,
                                                                  size=(self.MAX_LENGTH_BUFFER //
                                                                        self.settings['processing_settings']
                                                                        ['alongTrackAvg_ping']) *
                                                                       slice_dtype.itemsize)
        self.shmem_horizontal_slice_buffer = shared_memory.SharedMemory(name="shmem_horizontal_slice_buffer",
                                                                      create=False,
                                                                      size=(self.MAX_LENGTH_BUFFER //
                                                                            self.settings['processing_settings']
                                                                            ['alongTrackAvg_ping']) *
                                                                           slice_dtype.itemsize)
        self.shmem_timestamp_buffer_avg = shared_memory.SharedMemory(name="shmem_timestamp_buffer_avg", create=False,
                                                                     size=(self.MAX_LENGTH_BUFFER //
                                                                           self.settings['processing_settings']
                                                                           ['alongTrackAvg_ping']) *
                                                                          timestamp_dtype.itemsize)
        self.shmem_lat_lon_buffer_avg = shared_memory.SharedMemory(name="shmem_lat_lon_buffer_avg", create=False,
                                                                   size=(self.MAX_LENGTH_BUFFER //
                                                                         self.settings['processing_settings']
                                                                         ['alongTrackAvg_ping']) *
                                                                        lat_lon_dtype.itemsize)

        # Create numpy arrays from the shared memory
        self.amplitude_buffer = np.ndarray(shape=self.MAX_LENGTH_BUFFER, dtype=amplitude_dtype,
                                           buffer=self.shmem_amplitude_buffer.buf)
        self.count_buffer = np.ndarray(shape=self.MAX_LENGTH_BUFFER, dtype=count_dtype,
                                       buffer=self.shmem_count_buffer.buf)
        self.timestamp_buffer = np.ndarray(shape=self.MAX_LENGTH_BUFFER, dtype=timestamp_dtype,
                                           buffer=self.shmem_timestamp_buffer.buf)
        self.lat_lon_buffer = np.ndarray(shape=self.MAX_LENGTH_BUFFER, dtype=lat_lon_dtype,
                                         buffer=self.shmem_lat_lon_buffer.buf)

        self.vertical_slice_buffer = np.ndarray(shape=self.MAX_LENGTH_BUFFER // self.settings['processing_settings']
            ['alongTrackAvg_ping'], dtype=slice_dtype, buffer=self.shmem_vertical_slice_buffer.buf)
        self.horizontal_slice_buffer = np.ndarray(shape=self.MAX_LENGTH_BUFFER // self.settings['processing_settings']
            ['alongTrackAvg_ping'], dtype=slice_dtype, buffer=self.shmem_horizontal_slice_buffer.buf)
        self.timestamp_buffer_avg = np.ndarray(shape=self.MAX_LENGTH_BUFFER // self.settings['processing_settings']
            ['alongTrackAvg_ping'], dtype=timestamp_dtype, buffer=self.shmem_timestamp_buffer_avg.buf)
        self.lat_lon_buffer_avg = np.ndarray(shape=self.MAX_LENGTH_BUFFER // self.settings['processing_settings']
            ['alongTrackAvg_ping'], dtype=lat_lon_dtype, buffer=self.shmem_lat_lon_buffer_avg.buf)




        # self.amplitude_buffer = np.ndarray(shape=(self.MAX_LENGTH_BUFFER, self.MAX_NUM_GRID_CELLS, self.MAX_NUM_GRID_CELLS),
        #                                    dtype=np.float16, buffer=self.shmem_amplitude_buffer.buf)
        # print("id(amplitude_buffer in run): ", id(self.amplitude_buffer))

        # self.amplitude_buffer = NumpyRingBuffer(capacity=self.MAX_LENGTH_BUFFER, dtype=amplitude_dtype,
        #                                         buffer=self.shmem_amplitude_buffer.buf)
        # self.count_buffer = NumpyRingBuffer(capacity=self.MAX_LENGTH_BUFFER, dtype=count_dtype,
        #                                     buffer=self.shmem_count_buffer.buf)
        # self.timestamp_buffer = NumpyRingBuffer(capacity=self.MAX_LENGTH_BUFFER, dtype=timestamp_dtype,
        #                                         buffer=self.shmem_timestamp_buffer.buf)
        # self.lat_lon_buffer = NumpyRingBuffer(capacity=self.MAX_LENGTH_BUFFER, dtype=lat_lon_dtype,
        #                                       buffer=self.shmem_lat_lon_buffer.buf)

        self.get_and_buffer_pie()