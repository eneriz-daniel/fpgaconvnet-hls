import onnx
import onnxruntime
from google.protobuf import json_format

import fpgaconvnet.proto.fpgaconvnet_pb2
import fpgaconvnet.tools.onnx_helper as onnx_helper

from fpgaconvnet.hls.generate.partition import GeneratePartition

class GenerateNetwork:

    def __init__(self, name, partition_path, model_path):

        # save name
        self.name = name

        # load partition information
        self.partitions = fpgaconvnet.proto.fpgaconvnet_pb2.partitions()
        with open(partition_path,'r') as f:
           json_format.Parse(f.read(), self.partitions)

        # load onnx model
        self.model = onnx_helper.load(model_path)
        self.model = onnx_helper.update_batch_size(self.model, 1)
        # self.model = onnx_helper.update_batch_size(self.model,self.partition.batch_size)

        # add intermediate layers to outputs
        for node in self.model.graph.node:
            layer_info = onnx.helper.ValueInfoProto()
            layer_info.name = node.output[0]
            self.model.graph.output.append(layer_info)

        # add input aswell to output
        layer_info = onnx.helper.ValueInfoProto()
        layer_info.name = self.model.graph.input[0].name
        self.model.graph.output.append(layer_info)

        # remove input initializers
        name_to_input = {}
        inputs = self.model.graph.input
        for input in inputs:
            name_to_input[input.name] = input
        for initializer in self.model.graph.initializer:
            if initializer.name in name_to_input:
                inputs.remove(name_to_input[initializer.name])

        # inference session
        self.sess = onnxruntime.InferenceSession(self.model.SerializeToString())

        # create generator for each partition
        self.partitions_generator = [ GeneratePartition(
            self.name, partition, self.model, self.sess, f"partition_{i}") for \
                    i, partition in enumerate(self.partitions.partition) ]

    def apply_weight_quantisation(self):
        pass

    def generate_partition(self, partition_index):
        # generate each part of the partition
        self.partitions_generator[partition_index].generate_layers()
        self.partitions_generator[partition_index].generate_weights()
        self.partitions_generator[partition_index].generate_streams()
        self.partitions_generator[partition_index].generate_include()
        self.partitions_generator[partition_index].generate_source()
        self.partitions_generator[partition_index].generate_testbench()

        # create HLS project
        self.partitions_generator[partition_index].create_vivado_hls_project()

        # run c-synthesis
        self.partitions_generator[partition_index].run_csynth()

        # export IP package
        self.partitions_generator[partition_index].export_design()

    def generate_all_partitions(self, num_jobs=1):
        # TODO: add multi-threading for partitions
        for i in range(len(self.partitions_generator)):
            self.generate_partition(i)


