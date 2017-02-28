"""
.. Copyright 2017 EMBL-European Bioinformatics Institute
 
   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at 

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
"""

import os
import subprocess
import shlex

import numpy as np
import h5py

try:
    from pycompss.api.parameter import FILE_IN, FILE_OUT
    from pycompss.api.task import task
except ImportError :
    print "[Warning] Cannot import \"pycompss\" API packages."
    print "          Using mock decorators."
    
    from dummy_pycompss import *

from basic_modules.metadata import Metadata
from basic_modules.tool import Tool

# ------------------------------------------------------------------------------

class json3dIndexerTool(Tool):
    """
    Tool for running indexers over 3D JSON files for use in the RESTful API
    """
    
    def __init__(self):
        """
        Init function
        """
        print "3D JSON Model Indexer"
    
    
    
    def unzipJSON(self, file_targz):
        """
        Unzips the zipped folder containing all the models for regions of the
        genome based on the information within the adjacency matrixes generated
        by TADbit.
        
        Parameters
        ----------
        archive_location : str
            Location of archived JSON files
        
        Returns
        -------
        json_file_locations : list
            List of the locations of the files within an extracted archive
        
        Example
        -------
        .. code-block:: python
           :linenos:
           
           gz_file = '/home/<user>/test.tar.gz'
           json_files = unzip(gz_file)
        
        """
        targz_file_dir = targz_file.split("/")
        root_dir = '/'.join(targz_file_dir[0:len(targz_file_dir)-1])
        
        command_line = 'tar -xzf ' + file_tar
        args = shlex.split(command_line)
        p = subprocess.Popen(args)
        p.wait()
        
        from os import listdir
        from os.path import isfile, join
        
        onlyfiles = [join(root_dir, f) for f in listdir(root_dir) if isfile(join(root_dir, f))]
        
        return onlyfiles
    
    
    @task(json_files=IN, hdf5_file=FILE_INOUT)
    def json2hdf5(self, json_files, hdf5_file):
        """
        Genome Model Indexing
        
        Load the JSON files generated by TADbit into a specified HDF5 file. The
        file includes the x, y and z coordinates of all the models for each
        region along with the matching stats, clusters, TADs and adjacency
        values used during the modelling.
        
        Parameters
        ----------
        json_files : list
            Locations of all the JSON 3D model files generated by TADbit for a
            given dataset
        file_hdf5 : str
            Location of the HDF5 index file for this dataset.
        
        Example
        -------
        .. code-block:: python
           :linenos:
           
           if not self.json2hdf5(json_files, assembly, wig_file, hdf5_file):
               output_metadata.set_exception(
                   Exception(
                       "wig2hdf5: Could not process files {}, {}.".format(*input_files)))
        
        
        """
        
        for jf in json_files:
            models = json.loads(open(jf).read())
            
            metadata = models['metadata']
            objectdata = models['object']
            clusters = models['clusters']
            #file_name = jf.split("/")
            
            resolution = objectdata['resolution']
            
            uuid = objectdata['uuid']
            
            # Create the HDF5 file
            f = h5py.File(hdf5_file, "a")
            
            #print(file_name[-1] + ' - ' + file_name[-3] + "\t" + objectdata['chrom'][0] + ' : ' + str(objectdata['chromStart'][0]) + ' - ' + str(objectdata['chromEnd'][0]) + " | " + str(int(objectdata['chromEnd'][0]-objectdata['chromStart'][0])) + " - " + str(len(models['models'][0]['data'])))
            
            if str(resolution) in f:
                grp = f[str(resolution)]
                dset = grp['data']
                
                meta         = grp['meta']
                mpgrp        = meta['model_params']
                clustersgrp  = meta['clusters']
                centroidsgrp = meta['centroids']
            else:
                # Create the initial dataset with minimum values
                grp  = f.create_group(str(resolution))
                meta = grp.create_group('meta')
                
                mpgrp        = meta.create_group('model_params')
                clustersgrp  = meta.create_group('clusters')
                centroidsgrp = meta.create_group('centroids')
                
                dset = grp.create_dataset('data', (1, 1000, 3), maxshape=(None, 1000, 3), dtype='int32', chunks=True, compression="gzip")
                
                dset.attrs['title']          = objectdata['title']
                dset.attrs['experimentType'] = objectdata['experimentType']
                dset.attrs['species']        = objectdata['species']
                dset.attrs['project']        = objectdata['project']
                dset.attrs['identifier']     = objectdata['identifier']
                dset.attrs['assembly']       = objectdata['assembly']
                dset.attrs['cellType']       = objectdata['cellType']
                dset.attrs['resolution']     = objectdata['resolution']
                dset.attrs['datatype']       = objectdata['datatype']
                dset.attrs['components']     = objectdata['components']
                dset.attrs['source']         = objectdata['source']
                dset.attrs['TADbit_meta']    = json.dumps(metadata)
                dset.attrs['dependencies']   = json.dumps(objectdata['dependencies'])
                dset.attrs['restraints']     = json.dumps(models['restraints'])
                if 'hic_data' in models:
                    dset.attrs['hic_data']     = json.dumps(models['hic_data'])
            
            clustergrps = clustersgrp.create_group(str(uuid))
            for c in range(len(clusters)):
                clustersds = clustergrps.create_dataset(str(c), data=clusters[c], chunks=True, compression="gzip")
            
            centroidsds = centroidsgrp.create_dataset(str(uuid), data=models['centroids'], chunks=True, compression="gzip")
            
            current_size = len(dset)
            if current_size == 1:
                current_size = 0
            dset.resize((current_size+(len(models['models'][0]['data'])/3), 1000, 3))
            
            dnp = np.zeros([len(models['models'][0]['data'])/3, 1000, 3], dtype='int32')
            
            model_param = []
            
            model_id = 0
            for model in models['models']:
                ref = model['ref']
                d = model['data']
                
                cid = [ind for ind in xrange(len(clusters)) if ref in clusters[ind]]
                if len(cid) == 0:
                    cluster_id = len(clusters)
                else:
                    cluster_id = cid[0]
                
                model_param.append([int(ref), int(cluster_id)])
                
                j = 0
                for i in xrange(0, len(d), 3):
                    xyz = d[i:i + 3]
                    dnp[j][model_id] = xyz
                    j += 1
                
                model_id += 1
            
            model_param_ds = mpgrp.create_dataset(str(uuid), data=model_param, chunks=True, compression="gzip")
            
            model_param_ds.attrs['i']            = current_size
            model_param_ds.attrs['j']            = current_size+(len(models['models'][0]['data'])/3)
            model_param_ds.attrs['chromosome']   = objectdata['chrom'][0]
            model_param_ds.attrs['start']        = int(objectdata['chromStart'][0])
            model_param_ds.attrs['end']          = int(objectdata['chromEnd'][0])
            
            dset[current_size:current_size+(len(models['models'][0]['data'])/3), 0:1000, 0:3] += dnp
            
            f.close()
        
        return True
    
    
    def run(self, input_files, metadata):
        """
        Function to index models of the geome structure generated by TADbit on a
        per dataset basis so that they can be easily distributed as part of the
        RESTful API.
        
        Parameters
        ----------
        input_files : list
            gz_file : str
                Location of the archived JSON model files
            hdf5_file : str
                Location of the HDF5 index file
        meta_data : list
            file_id : str
                file_id used to identify the original wig file
            assembly : str
                Genome assembly accession
        
        Returns
        -------
        list
            hdf5_file : str
                Location of the HDF5 index file
        
        Example
        -------
        .. code-block:: python
           :linenos:
           
           import tool
           
           # WIG Indexer
           w = tool.json3dIndexerTool(self.configuration)
           wi, wm = w.run((gz_file, hdf5_file_id), ())
        """
        
        targz_file   = input_files[0]
        
        hdf5_name = targz_file.split("/")
        hdf5_name[-1].replace('.tar.gz', '.hdf5')
        hdf5_file = '/'.join(hdf5_name)
        
        source_file_id = meta_data['file_id']
        
        json_files = self.unzip(targz_file)
        
        # handle error
        if not self.json2hdf5(source_file_id, json_files, hdf5_file):
            output_metadata.set_exception(
                Exception(
                    "json2hdf5: Could not process files {}, {}.".format(*input_files)))
        
        return ([hdf5_file], [output_metadata])