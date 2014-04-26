#!/usr/bin/env python
#  class to convert/process modis data using gdal
#
#  Some code is coming from GDAL/OGR Test Suite
#  Copyright (c) 2008, Andrey Kiselev <dron16@ak4719.spb.edu>
#  Copyright (c) 2008-2014, Even Rouault <even dot rouault at mines-paris dot org>
#  http://trac.osgeo.org/gdal/browser/trunk/autotest/alg/warp.py#L782
#
#  (c) Copyright Luca Delucchi 2014
#  Authors: Luca Delucchi
#  Email: luca dot delucchi at iasma dot it
#
##################################################################
#
#  This MODIS Python class is licensed under the terms of GNU GPL 2.
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License as
#  published by the Free Software Foundation; either version 2 of
#  the License, or (at your option) any later version.
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#  See the GNU General Public License for more details.
#
##################################################################

try:
    import osgeo.gdal as gdal
except ImportError:
    try:
        import gdal
    except ImportError:
        raise('Python GDAL library not found, please install python-gdal')

try:
    import osgeo.osr as osr
except ImportError:
    try:
        import osr
    except ImportError:
        raise('Python GDAL library not found, please install python-gdal')


RESAM_GDAL = ['AVERAGE', 'BILINEAR', 'CUBIC', 'CUBIC_SPLINE', 'LANCZOS',
              'MODE', 'NEAREST_NEIGHBOR']
sinusoidal_wkt = 'PROJCS["Sinusoidal_Sanson_Flamsteed",GEOGCS["GCS_Unknown",' \
                 'DATUM["D_unknown",SPHEROID["Unknown",6371007.181,"inf"]],' \
                 'PRIMEM["Greenwich",0],UNIT["Degree",0.017453292519943295]]' \
                 ',PROJECTION["Sinusoidal"],PARAMETER["central_meridian",0],' \
                 'PARAMETER["false_easting",0],PARAMETER["false_northing",0]' \
                 ',UNIT["Meter",1]]'


def getResampling(r):
    """Return  the GDAL resampling method"""
    if r == 'AVERAGE':
        return gdal.GRA_Average
    elif r == 'BILINEAR' or r == 'BICUBIC':
        return gdal.GRA_Bilinear
    elif r == 'LANCZOS':
        return gdal.GRA_Lanczos
    elif r == 'MODE':
        return gdal.GRA_Mode
    elif r == 'NEAREST_NEIGHBOR':
        return gdal.GRA_NearestNeighbour
    elif r == 'CUBIC_CONVOLUTION' or r == 'CUBIC':
        return gdal.GRA_Cubic
    elif r == 'CUBIC_SPLINE':
        return gdal.GRA_CubicSpline


class convertModisGDAL:
    """A class to convert modis data from hdf to GDAL formats using GDAL
    """
    def __init__(self, hdfname, prefix, subset, res, outformat="GTiff",
                 epsg=None, wkt=None, resampl='NEAREST_NEIGHBOR'):
        # Open source dataset
        self.in_name = hdfname
        self.src_ds = gdal.Open(self.in_name)
        self.layers = self.src_ds.GetSubDatasets()
        self.output_pref = prefix
        self.resolution = res
        if epsg:
            self.dst_srs = osr.SpatialReference()
            self.dst_srs.ImportFromEPSG(int(epsg))
            self.dst_wkt = self.dst_srs.ExportToWkt()
        elif wkt:
            try:
                f = open(wkt)
                self.dst_wkt = f.read()
                f.close()
            except:
                self.dst_wkt = wkt
        else:
            raise IOError('You have to set one of the following option: '
                          '"epsg", "wkt"')
        # error threshold the same value as gdalwarp
        self.error_threshold = 0.125
        self.resampling = getResampling(resampl)
        self.subset = subset.replace('(', '').replace(')', '').strip().split()
        self.driver = gdal.GetDriverByName(outformat)
        if self.driver is None:
            raise IOError('Format driver %s not found, pick a supported '
                          'driver.' % outformat)

    def _boundingBox(self, src):
        """Obtain the bounding box of raster in the new coordinate system"""
        src_gtrn = src.GetGeoTransform(can_return_null=True)

        src_bbox_cells = ((0., 0.), (0, src.RasterYSize), (src.RasterXSize, 0),
                          (src.RasterXSize, src.RasterYSize))

        geo_pts_x = []
        geo_pts_y = []
        for x, y in src_bbox_cells:
            x2 = src_gtrn[0] + src_gtrn[1] * x + src_gtrn[2] * y
            y2 = src_gtrn[3] + src_gtrn[4] * x + src_gtrn[5] * y
            geo_pts_x.append(x2)
            geo_pts_y.append(y2)
        return ((min(geo_pts_x), min(geo_pts_y)), (max(geo_pts_x),
                 max(geo_pts_y)))

    def _calculateRes(self, mi, ma, res):
        """Calculate the number of pixel from extent and resolution

        mi = minimum value of extent
        ma = maximum value of extent
        res = resolution of output raster
        """
        return int(round((ma - mi) / res))

    def _createWarped(self):
        """Create a warped VRT file to fetch default values for target raster
        dimensions and geotransform"""
        src = gdal.Open(self.layers[0][0])
        tmp_ds = gdal.AutoCreateWarpedVRT(src, sinusoidal_wkt,
                                          self.dst_wkt, self.resampling,
                                          self.error_threshold)

        if not self.resolution:
            self.dst_xsize = tmp_ds.RasterXSize
            self.dst_ysize = tmp_ds.RasterYSize
            self.dst_gt = tmp_ds.GetGeoTransform()
        else:
            bbox = self._boundingBox(tmp_ds)
            self.dst_xsize = self._calculateRes(bbox[0][0], bbox[1][0],
                                                self.resolution)
            self.dst_ysize = self._calculateRes(bbox[0][1], bbox[1][1],
                                                self.resolution)
            if self.dst_xsize == 0:
                raise IOError('Invalid number of pixel 0 for X size')
                return 0
            elif self.dst_ysize == 0:
                raise IOError('Invalid number of pixel 0 for Y size')
                return 0
            self.dst_gt = [bbox[0][0], self.resolution, 0.0, bbox[1][1], 0.0,
                           -self.resolution]
        tmp_ds = None
        src = None
        return 0

    def _progressCallback(self, pct, message, user_data):
        #print(pct)
        return 1  # 1 to continue, 0 to stop

    def _reprojectOne(self, l):
        """Reproject a single subset of MODIS product

        l = complete name of input dataset
        """
        l_src_ds = gdal.Open(l)
        meta = l_src_ds.GetMetadata()
        band = l_src_ds.GetRasterBand(1)
        if '_FillValue' in meta.keys():
            fill_value = meta['_FillValue']
        else:
            fill_value = None
        datatype = band.DataType
        l_name = l[1].split(' ')[1]
        out_name = "{pref}_{lay}.tif".format(pref=self.output_pref, lay=l_name)
        try:
            dst_ds = self.driver.Create(out_name, self.dst_xsize,
                                        self.dst_ysize, 1, datatype)
        except:
            raise IOError('Not possibile to create dataset %s' % out_name)
            return 0
        dst_ds.SetProjection(self.dst_wkt)
        dst_ds.SetGeoTransform(self.dst_gt)
        if fill_value:
            dst_ds.GetRasterBand(1).SetNoDataValue(float(fill_value))
            dst_ds.GetRasterBand(1).Fill(float(fill_value))
        cbk = self._progressCallback
        # value for last parameter of above self._progressCallback
        cbk_user_data = None
        try:
            gdal.ReprojectImage(l_src_ds, dst_ds, sinusoidal_wkt, self.dst_wkt,
                                self.resampling, 0, self.error_threshold, cbk,
                                cbk_user_data)
            print "Layer %s reprojected" % l[0]
        except:
            raise IOError('Not possibile to reproject dataset %s' % l[0])
            return 0
        dst_ds.SetMetadata(meta)
        dst_ds = None
        l_src_ds = None
        return 0

    def run(self):
        """Reproject all the subset of choosen layer"""
        self._createWarped()
        n = 0
        for i in self.subset:
            print i
            if i == '1':
                self._reprojectOne(self.layers[n][0])
            n = n + 1
        print "All layer for dataset %s reprojected" % self.in_name


# =============================================================================
def raster_copy(s_fh, s_xoff, s_yoff, s_xsize, s_ysize, s_band_n,
                t_fh, t_xoff, t_yoff, t_xsize, t_ysize, t_band_n,
                nodata=None):
    """Copy a band of raster into the output file.

        Function copied from gdal_merge.py
    """
    if nodata is not None:
        return raster_copy_with_nodata(s_fh, s_xoff, s_yoff, s_xsize, s_ysize,
                                       s_band_n, t_fh, t_xoff, t_yoff, t_xsize,
                                       t_ysize, t_band_n, nodata)

    s_band = s_fh.GetRasterBand(s_band_n)
    t_band = t_fh.GetRasterBand(t_band_n)

    data = s_band.ReadRaster(s_xoff, s_yoff, s_xsize, s_ysize,
                             t_xsize, t_ysize, t_band.DataType)
    t_band.WriteRaster(t_xoff, t_yoff, t_xsize, t_ysize, data, t_xsize,
                       t_ysize, t_band.DataType)

    return 0


def raster_copy_with_nodata(s_fh, s_xoff, s_yoff, s_xsize, s_ysize, s_band_n,
                            t_fh, t_xoff, t_yoff, t_xsize, t_ysize, t_band_n,
                            nodata):
    """Copy a band of raster into the output file with nodata values.

        Function copied from gdal_merge.py
    """
    try:
        import numpy as Numeric
    except ImportError:
        import Numeric

    s_band = s_fh.GetRasterBand(s_band_n)
    t_band = t_fh.GetRasterBand(t_band_n)

    data_src = s_band.ReadAsArray(s_xoff, s_yoff, s_xsize, s_ysize,
                                  t_xsize, t_ysize)
    data_dst = t_band.ReadAsArray(t_xoff, t_yoff, t_xsize, t_ysize)

    nodata_test = Numeric.equal(data_src, nodata)
    to_write = Numeric.choose(nodata_test, (data_src, data_dst))

    t_band.WriteArray(to_write, t_xoff, t_yoff)

    return 0


class file_info:
    """A class holding information about a GDAL file.

       Class copied from gdal_merge.py
    """

    def init_from_name(self, filename):
        """
        Initialize file_info from filename

        filename -- Name of file to read.

        Returns 1 on success or 0 if the file can't be opened.
        """
        fh = gdal.Open(filename)
        if fh is None:
            return 0

        self.filename = filename
        self.bands = fh.RasterCount
        self.xsize = fh.RasterXSize
        self.ysize = fh.RasterYSize
        self.band_type = fh.GetRasterBand(1).DataType
        self.projection = fh.GetProjection()
        self.geotransform = fh.GetGeoTransform()
        self.ulx = self.geotransform[0]
        self.uly = self.geotransform[3]
        self.lrx = self.ulx + self.geotransform[1] * self.xsize
        self.lry = self.uly + self.geotransform[5] * self.ysize

        meta = fh.GetMetadata()
        if '_FillValue' in meta.keys():
            self.fill_value = meta['_FillValue']
        else:
            self.fill_value = None

        ct = fh.GetRasterBand(1).GetRasterColorTable()
        if ct is not None:
            self.ct = ct.Clone()
        else:
            self.ct = None

        return 1

    def copy_into(self, t_fh, s_band=1, t_band=1, nodata_arg=None):
        """
        Copy this files image into target file.

        This method will compute the overlap area of the file_info objects
        file, and the target gdal.Dataset object, and copy the image data
        for the common window area.  It is assumed that the files are in
        a compatible projection ... no checking or warping is done.  However,
        if the destination file is a different resolution, or different
        image pixel type, the appropriate resampling and conversions will
        be done (using normal GDAL promotion/demotion rules).

        t_fh -- gdal.Dataset object for the file into which some or all
        of this file may be copied.

        Returns 1 on success (or if nothing needs to be copied), and zero one
        failure.
        """
        t_geotransform = t_fh.GetGeoTransform()
        t_ulx = t_geotransform[0]
        t_uly = t_geotransform[3]
        t_lrx = t_geotransform[0] + t_fh.RasterXSize * t_geotransform[1]
        t_lry = t_geotransform[3] + t_fh.RasterYSize * t_geotransform[5]

        # figure out intersection region
        tgw_ulx = max(t_ulx, self.ulx)
        tgw_lrx = min(t_lrx, self.lrx)
        if t_geotransform[5] < 0:
            tgw_uly = min(t_uly, self.uly)
            tgw_lry = max(t_lry, self.lry)
        else:
            tgw_uly = max(t_uly, self.uly)
            tgw_lry = min(t_lry, self.lry)

        # do they even intersect?
        if tgw_ulx >= tgw_lrx:
            return 1
        if t_geotransform[5] < 0 and tgw_uly <= tgw_lry:
            return 1
        if t_geotransform[5] > 0 and tgw_uly >= tgw_lry:
            return 1

        # compute target window in pixel coordinates.
        tw_xoff = int((tgw_ulx - t_geotransform[0]) / t_geotransform[1] + 0.1)
        tw_yoff = int((tgw_uly - t_geotransform[3]) / t_geotransform[5] + 0.1)
        tw_xsize = int((tgw_lrx - t_geotransform[0]) / t_geotransform[1] + 0.5) - tw_xoff
        tw_ysize = int((tgw_lry - t_geotransform[3]) / t_geotransform[5] + 0.5) - tw_yoff

        if tw_xsize < 1 or tw_ysize < 1:
            return 1

        # Compute source window in pixel coordinates.
        sw_xoff = int((tgw_ulx - self.geotransform[0]) / self.geotransform[1])
        sw_yoff = int((tgw_uly - self.geotransform[3]) / self.geotransform[5])
        sw_xsize = int((tgw_lrx - self.geotransform[0])
                       / self.geotransform[1] + 0.5) - sw_xoff
        sw_ysize = int((tgw_lry - self.geotransform[3])
                       / self.geotransform[5] + 0.5) - sw_yoff

        if sw_xsize < 1 or sw_ysize < 1:
            return 1

        # Open the source file, and copy the selected region.
        s_fh = gdal.Open(self.filename)

        return \
            raster_copy(s_fh, sw_xoff, sw_yoff, sw_xsize, sw_ysize, s_band,
                        t_fh, tw_xoff, tw_yoff, tw_xsize, tw_ysize, t_band,
                        nodata_arg)


class createMosaicGDAL:
    """A class to mosaic modis data from hdf to GDAL formats using GDAL"""
    def __init__(self, hdfnames, output, subset, res, outformat="HDF4Image"):
        # Open source dataset
        self.in_names = hdfnames
        self.output_pref = output
        self.resolution = res
        self.subset = subset.replace('(', '').replace(')', '').strip().split()
        self.driver = gdal.GetDriverByName(outformat)
        if self.driver is None:
            raise IOError('Format driver %s not found, pick a supported '
                          'driver.' % outformat)
            return 0
        DriverMD = self.driver.GetMetadata()
        if 'DCAP_CREATE' not in DriverMD:
            raise IOError('Format driver %s does not support creation and'
                          ' piecewise writing.\nPlease select a format that'
                          ' does, such as GTiff (the default) or HFA (Erdas'
                          ' Imagine).' % format)
        self._initLayers()
        self._getUsedLayers()

    def _initLayers(self):
        """Set up the variable self.layers as dictionary for each choosen 
        subset"""
        src_ds = gdal.Open(self.in_names[0])
        layers = src_ds.GetSubDatasets()
        self.layers = {}
        n = 0
        for i in self.subset:
            if i == '1':
                name = layers[n][0].split(':')[-1]
                self.layers[name] = []
            n = n + 1

    def _getUsedLayers(self):
        """Add each subset to the correct list for each input layers"""
        for name in self.in_names:
            src_ds = gdal.Open(name)
            layers = src_ds.GetSubDatasets()
            n = 0
            for i in self.subset:
                if i == '1':
                    name = layers[n][0].split(':')[-1]
                    self.layers[name].append(layers[n][0])
                n = n + 1

    def _names_to_fileinfos(self):
        """Translate a list of GDAL filenames, into file_info objects.
        Returns a list of file_info objects. There may be less file_info
        objects than names if some of the names could not be opened as GDAL files.
        """
        self.file_infos = {}
        for k, v in self.layers.iteritems():
            self.file_infos[k] = []
            for name in v:
                fi = file_info()
                if fi.init_from_name(name) == 1:
                    self.file_infos[k].append(fi)
        self.file_infos

    def write_mosaic_xml(self):
        """Write the XML metadata file for MODIS mosaic"""
        from parsemodis import parseModisMulti
        import os
        listHDF = []
        for i in self.in_names:
            listHDF.append(os.path.realpath(i.strip()))
        pmm = parseModisMulti(listHDF)
        pmm.writexml("%s.xml" % self.output_pref)

    def run(self):
        """Execute the mosaik  """
        self._names_to_fileinfos()
        values = self.file_infos.values()
        l1 = values[0][0]
        ulx = l1.ulx
        uly = l1.uly
        lrx = l1.lrx
        lry = l1.lry
        for fi in self.file_infos[self.file_infos.keys()[0]]:
            ulx = min(ulx, fi.ulx)
            uly = max(uly, fi.uly)
            lrx = max(lrx, fi.lrx)
            lry = min(lry, fi.lry)
        psize_x = l1.geotransform[1]
        psize_y = l1.geotransform[5]
        band_type = l1.band_type
        geotransform = [ulx, psize_x, 0, uly, 0, psize_y]
        xsize = int((lrx - ulx) / geotransform[1] + 0.5)
        ysize = int((lry - uly) / geotransform[5] + 0.5)
        #t_fh = self.driver.Create(self.output_pref, xsize, ysize, 1, band_type)
        t_fh = self.driver.Create(self.output_pref, xsize, ysize,
                                  len(self.file_infos.keys()), band_type)
        if t_fh is None:
            raise IOError('Not possibile to create dataset %s' % self.output_pref)
            return

        t_fh.SetGeoTransform(geotransform)
        t_fh.SetProjection(l1.projection)
        i = 1
        for names in self.file_infos.values():
            fill = None
#            if i > 1:
#                t_fh.AddBand(names[0].band_type)
            if names[0].fill_value:
                fill = float(names[0].fill_value)
                t_fh.GetRasterBand(i).SetNoDataValue(fill)
                t_fh.GetRasterBand(i).Fill(fill)
            for n in names:
                n.copy_into(t_fh, 1, i, fill)
            i = i + 1
        self.write_mosaic_xml()
        t_fh = None