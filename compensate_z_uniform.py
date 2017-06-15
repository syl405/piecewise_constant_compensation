import csv
import re
import sys
sys.path.append('libs\\python-gcode\\')

import gcode

#define global parameters
Z_CONTROL_RESOLUTION = 0.0105833 #mm per full step

def compensate_z_uniform(lookup_table_path, gcode_path):
	# Validate arguments
	if not type(lookup_table_path) is str:
		raise TypeError('Unexpected data type for argument lookup_table_path. Expecting str.')
	elif not lookup_table_path.endswith('.csv'):
		raise ValueError('Unexpected file type for lookup table specified. Expecting .csv file.')
	elif not type(gcode_path) is str:
		raise TypeError('Unexpected data type for argument gcode_path. Expecting str.')
	elif not gcode_path.endswith('.gcode'):
		raise ValueError('Unexpected file type for gcode file specified. Expecting .gcode file.')

	# Parse in lookup table
	with open(lookup_table_path) as lookup_table_fs:
		lookup_table = [[],[],[]];
		try:
			reader = csv.reader(lookup_table_fs)
			for line in reader:
				lookup_table[0].append(float(line[0])) #start height
				lookup_table[1].append(float(line[1])) #end height
				lookup_table[2].append(float(line[2])) #compensation
		except:
			raise ValueError('Failed to parse in lookup table from CSV file.')

	# Instantiate compensator using parsed in data
	piecewise_compensator = LayerwiseCompensator(lookup_table)

	# Instantiate Gcode object
	g = gcode.Gcode(gcode_path)

	# Apply Z-offset to individual layers
	outstanding_offset_to_apply = 0 #cumulative variable for remaining offset to apply
	for i in range(0,len(g.layers)):
		cur_build_height = g.layers[i].z() #get build height for this layer
		offset_reqd = piecewise_compensator.get_total_offset(cur_build_height)
		outstanding_offset_to_apply += offset_reqd
		if outstanding_offset_to_apply >= Z_CONTROL_RESOLUTION:
			(num_steps_to_apply,residual_offset) = divmod(outstanding_offset_to_apply,Z_CONTROL_RESOLUTION)
			g.shift(i,Z=num_steps_to_apply*Z_CONTROL_RESOLUTION) #apply offset in full Z steps only
			outstanding_offset_to_apply = residual_offset #keep track of remaining offset to apply

	# Output Z-compensated G-code
	g.construct(gcode_path[0:-6] + '_compensated.gcode')

class LayerwiseCompensator:
	def __init__(self, lookup_table):
		"""
		takes a 3-member list of lists, specifying:
		- block start build height (exclusive except first block)
		- block end build height (inclusive)
		- per layer compensation in this block (in mm, positive = thicker layers)
		"""
		# check argument type and length
		if not type(lookup_table) is list:
			raise TypeError("Unexpected data type for argument lookup_table. Expecting list.")
		elif not len(lookup_table) == 3:
			raise ValueError("Unexpected length for argument lookup_table. Expecting list of length 3.")
		
		# check length of sublists in lookup_table
		member_lengths = []
		for member in lookup_table:
			member_lengths.append(len(member))
		if not len(set(member_lengths)) == 1: #verify that all member lists are of same length
			raise ValueError('Lengths of member list in lookup_table must agree.')

		self.blocks = []
		for i in range(0,member_lengths[0]):
			 self.blocks.append(Block(lookup_table[0][i],lookup_table[1][i],lookup_table[2][i]))
		self.blocks.append(Block(lookup_table[1][-1],float('inf'),lookup_table[2][-1])) #extrapolate past error model to keep same per layer offset from last block
		self.blocks = tuple(self.blocks) #convert to tuple to protect against accidental editing downstream

	def get_total_offset(self, build_height):
		"""
		Returns sum of offsets specified by (potentially overlapping) blocks.
		This summing behavior allows more complex conditional compensation schemes.
		When blocks are non-overlapping, simply return the appropriate offset for the given build height
		"""
		total_offset = 0;
		for block in self.blocks:
			total_offset += block.get_offset(build_height)
		return total_offset

class Block:
	def __init__(self,start_height,end_height,compensation):
		self.start_height = start_height
		self.end_height = end_height
		self.compensation = compensation

	def get_offset(self, build_height):
		"""
		Takes a a build height specifying the nominal height of the top surface of a layer.
		Returns a compensation value to apply (positive = thicker layer).
		Returns 0 if build_height is out of the height range specified for this block.
		"""
		if build_height > self.start_height and build_height <= self.end_height:
			return self.compensation
		else:
			return 0
