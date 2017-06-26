import csv
import re
import sys
sys.path.append('libs\\python-gcode\\')

import gcode
reload(gcode)

#define global parameters
Z_CONTROL_RESOLUTION = 0.0105833 #mm per full step

def compensate_z_3d(model_coefficients_path, gcode_path):
	# Validate arguments
	if not type(model_coefficients_path) is str:
		raise TypeError('Unexpected data type for argument lookup_table_path. Expecting str.')
	elif not model_coefficients_path.endswith('.csv'):
		raise ValueError('Unexpected file type for lookup table specified. Expecting .csv file.')
	elif not type(gcode_path) is str:
		raise TypeError('Unexpected data type for argument gcode_path. Expecting str.')
	elif not gcode_path.endswith('.gcode'):
		raise ValueError('Unexpected file type for gcode file specified. Expecting .gcode file.')

	# Parse in lookup table
	with open(model_coefficients_path) as model_coefficients_fs:
		coefficients = [];
		try:
			reader = csv.reader(model_coefficients_fs)
			for line in reader:
				coefficients.append(line[0])
		except:
			raise ValueError('Failed to parse in lookup table from CSV file.')

	# Instantiate compensator using parsed in data
	compensator_model = Compensator3D(coefficients[0],coefficients[1],coefficients[2],3.9)

	# Instantiate Gcode object
	g = gcode.Gcode(gcode_path)

	# Apply model-based Z compensation
	g.z_compensate(compensator_model)

	# Output Z-compensated G-code
	g.construct(gcode_path[0:-6] + '_3d_compensated.gcode')

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

class Compensator3D:
	def __init__(self, x_coeff, y_coeff, z_coeff, model_z_offset):
		self.x_coeff = float(x_coeff)
		self.y_coeff = float(y_coeff)
		self.z_coeff = float(z_coeff)
		self.model_z_offset = float(model_z_offset)

	def get_predicted_error(self, x, y, z):
		"""Returns a height error (delta_z) predicted by the model, given nominal
		coordinates of x, y, and z."""
		true_z = z - self.model_z_offset #error model is referenced off of a 3.9 mm-thick reference plane instead of the bottom of the part
		if true_z < 0:
			return 0
		else:
			return self.x_coeff*x + self.y_coeff*y + self.z_coeff*true_z
