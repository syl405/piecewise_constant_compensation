"""
Based on python_gcode (https://github.com/fetlab/python_gcode) by (https://github.com/anjiro).
Licensed and modified under the MIT License by Shien Yang Lee (https://github.com/syl405).
"""

import re, sys, warnings, copy
SEG_LENGTH_SPLIT = 3 #segment lengths to split moves into (in mm)

class Point(object):
	def __init__(self, X, Y, Z):
		self.X = float(X)
		self.Y = float(Y)
		self.Z = float(Z)

	def __repr__(self):
		return '(%f,%f,%f)' % (self.X, self.Y, self.Z)


	def get_coordinates(self):
		"""returns XYZ coordinates of this point as a 3-member list"""
		return [self.X, self.Y, self.Z]

class Line(object):
	def __init__(self, line, initial_point, code=None, args={}, comment=None, explicit=False):
		"""Parse a single line of gcode into its code and named
		arguments."""
		self.line    = line
		self.code    = code
		self.args    = args
		self.comment = comment
		self.initial_point = initial_point

		if args or code:
			if not (args and code):
				raise ValueError("Both code and args must be specified")
		else:
			#Check for comment-only lines
			if re.match(r'\s*;', line):
				self.comment = line[line.index(';')+1:]
			else:
				#Extract the comment if there is one
				lc = self.line.split(';', 1)
				if len(lc) > 1:
					self.line, self.comment = lc

				#Get the actual code and the arguments
				args = self.line.split()
				self.code = args[0]
				self.args = {}
				if self.code == 'M117' or self.code == 'M38' or self.code == '\\nM38':
					self.args[None] = self.line.split(None, 1)[1]
				else:
					for arg in args[1:]:
						if re.match('[A-Za-z]', arg[0]):
							if arg[1:] is not None and arg[1:] != '':
								try:
									#only convert to float if decimal point present
									self.args[arg[0]] = float(arg[1:])\
									 if '.' in arg[1:]\
									  else int(arg[1:]) 
								except ValueError:
									sys.stderr.write("Line: %s\n" % line)
									sys.stderr.write("Code: %s\n" % self.code)
									sys.stderr.write("args: %s\n" % args)
									raise
							else:
								self.args[arg[0]] = None
						else:
							self.args[None] = arg

		# determine destination specified by current line
		[X,Y,Z] = self.initial_point.get_coordinates() #default to no movemente
		# update with destination specified in current line if applicable
		if self.code in {'G0','G1'}:
			if 'X' not in self.args and \
			'Y' not in self.args and \
			'Z' not in self.args and \
			'E' in self.args:
				self.args = self.args
				#do not force explicit XYZ for filament-only moves (ometimes in relative mode)
			else:
				if 'X' in self.args:
					X = self.args['X']
				#force explicit XYZ dest if explicit specified
				elif explicit: 
					self.args['X'] = X
				if 'Y' in self.args:
					Y = self.args['Y']
				elif explicit:
					self.args['Y'] = Y
				if 'Z' in self.args:
					Z = self.args['Z']
				elif explicit:
					self.args['Z'] = Z
			self.final_point = Point(X,Y,Z)
		else:
			self.final_point = self.initial_point

		self.length = self.get_length()

		#sanity check: do not allow negative vector magnitudes
		if self.length < 0:
			raise ValueError('Negative vector magnitude detected.')

	def __repr__(self):
		return self.construct()
		return '%s: %s' % (self.code, repr(self.args))

	def get_length(self):
		"""returns length of current line in 3-space (XYZ)"""
		return ((self.final_point.get_coordinates()[0]\
			     -self.initial_point.get_coordinates()[0])**2  +\
				(self.final_point.get_coordinates()[1]\
				 -self.initial_point.get_coordinates()[1])**2 + \
				(self.final_point.get_coordinates()[2]\
				 -self.initial_point.get_coordinates()[2])**2)**0.5 # pythagorus' theorem

	def get_code(self):
		return self.code

	def get_args(self):
		return self.args

	def get_initial_point(self):
		return self.initial_point

	def get_final_point(self):
		return self.final_point

	def split_move(self,segment_length):
		"""if current move is longer than segment_length (provided in mm), 
		split into segments of specified length (put single short line from remainder at end)
		and return list of lines. else return single-element list containing self."""

		if self.length <= segment_length:
			return [self]
		else:
			#calculate number of segments into which to split current line; short segment at end
			n_segments = int(self.length//segment_length)

			#calculate direction cosines
			if 'X' in self.args:
				X_hat = (self.args['X'] - self.initial_point.get_coordinates()[0])/float(self.length)
			else:
				X_hat = float(0)
			if 'Y' in self.args:
				Y_hat = (self.args['Y'] - self.initial_point.get_coordinates()[1])/float(self.length)
			else:
				Y_hat = float(0)
			if 'Z' in self.args:
				Z_hat = (self.args['Z'] - self.initial_point.get_coordinates()[2])/float(self.length)
			else:
				Z_hat = float(0)

			#debug
			if self.line == 'G0 X0 Y1000 F10800.0 ':
				print 'direction: (%f,%f,%f)' % (X_hat,Y_hat,Z_hat)
				print 'magnitude: %f' % self.length
				print 'initial: (%f,%f,%f)' % (
					self.initial_point.get_coordinates()[0],
					self.initial_point.get_coordinates()[1],
					self.initial_point.get_coordinates()[2])
				print 'final: (%f,%f,%f)' % (
					self.final_point.get_coordinates()[0],
					self.final_point.get_coordinates()[1],
					self.final_point.get_coordinates()[2])

			#calculate extrusion length for each segment
			E_full_length_segments = round(self.args['E'] *\
				(float(segment_length)/self.length),3) #distribute filament length by print length
			E_last_segment = round(self.args['E'] *\
				((self.length - (float(segment_length)*n_segments))/self.length),3)

			#instantiate first line (this is redundant move with zero length)
			first_line_args = copy.deepcopy(self.args)
			first_line_args['X'] = self.get_initial_point().get_coordinates()[0]
			first_line_args['Y'] = self.get_initial_point().get_coordinates()[1]
			first_line_args['Z'] = self.get_initial_point().get_coordinates()[2]
			first_line_args['E'] = 0
			list_of_constituent_lines = [Line('',\
										 self.get_initial_point(),\
										 self.code,\
										 first_line_args,\
										 'begin splt')]

			for i in range(1,n_segments+1): #exclude redundant first line
				cur_X = round(self.initial_point.get_coordinates()[0] + i*segment_length*X_hat,3)
				cur_Y = round(self.initial_point.get_coordinates()[1] + i*segment_length*Y_hat,3)
				cur_Z = round(self.initial_point.get_coordinates()[2] + i*segment_length*Z_hat,3)

				#make next segment
				cur_args = copy.deepcopy(self.args) #copy over arguments from unsplit line
				#update XYZ destination with incremental values
				cur_args['X'] = cur_X
				cur_args['Y'] = cur_Y
				cur_args['Z'] = cur_Z
				cur_args['E'] = E_full_length_segments
				if i > 1 and 'F' in cur_args: #explicitly specify feedrate only for first segment
					del cur_args['F']
				incremental_line = Line(
					'', 
					list_of_constituent_lines[-1].get_final_point(), 
					self.code, cur_args, 
					'splt')


				#append next segment to list of split moves
				list_of_constituent_lines.append(incremental_line)

			#instantiate last time (this segment may be shorter than the specified segment length)
			last_line_args = copy.deepcopy(self.args)
			last_line_args['E'] = E_last_segment
			if 'F' in last_line_args: #do not explicitly specify feedrate for last line
				del last_line_args['F']
			last_line = Line(
				'', 
				list_of_constituent_lines[-1].get_final_point(), 
				self.code, last_line_args, 
				'end splt')
			list_of_constituent_lines.append(last_line)

			#remove redundant first line (a redundant line going nowhere causes printer to hesitate)
			del list_of_constituent_lines[0]

			#sanity check
			if list_of_constituent_lines[-1].get_final_point().get_coordinates() != \
			self.final_point.get_coordinates():
				raise ValueError('Split line not coming back to original destination.')

			return list_of_constituent_lines

	def construct(self):
		"""Construct and return a line of gcode based on self.code and
		self.args."""
		if not self.code:
			return ';%s' % self.comment
		return ' '.join([self.code] +
				['%s%s' % (k if k is not None else '', v if v is not None else '')
					for k,v in self.args.iteritems()]) +\
		(' ;%s' % self.comment if self.comment else '')

class Layer(object):
	def __init__(self, prev_layer_final_pt, lines=[], split=True, layernum=None, explicit=True):
		"""Parse a layer of gcode line-by-line, making Line objects."""
		self.layernum  = layernum
		self.preamble  = []
		self.postamble = []
		self.lines = []

		first_line_in_layer = Line(
		lines[0],
		prev_layer_final_pt,
		explicit=explicit) #make Line object from unsplit first line
		if first_line_in_layer.get_code() in ['G0','G1'] and split: #only split move lines
			split_first_line_in_layer = first_line_in_layer.split_move(SEG_LENGTH_SPLIT)
			self.lines += split_first_line_in_layer # initialize list of lines with split 1st line
		else:
			self.lines += [first_line_in_layer]

		for l in lines[1:]:
			prev_line = self.lines[-1]
			cur_line = Line(l,prev_line.get_final_point(),explicit=explicit)
			if cur_line.get_code() in ['G0','G1'] and 'E' in cur_line.get_args() and split:
				split_cur_line = cur_line.split_move(SEG_LENGTH_SPLIT)
				self.lines += split_cur_line
			else:
				self.lines += [cur_line]

		#calculate initial and final points in this layer
		self.initial_point = self.lines[0].get_initial_point() #intial pt in first line
		self.final_point = self.lines[-1].get_final_point() #final pt in last line

	def __repr__(self):
		return '<Layer %s at Z=%s; corners: (%s, %s), (%d, %d); %d lines>' % (
				(self.layernum, self.z()) + self.extents() + (len(self.lines),))

	def get_initial_point(self):
		"""returns first XYZ coordinate point in this layer"""
		return self.initial_point

	def get_final_point(self):
		"""returns last XYZ coordinate point in this layer"""
		return self.final_point

	def extents(self):
		"""Return the extents of the layer: the min/max in x and y that
		occur. Note this does not take arcs into account."""
		min_x = min(self.lines, key=lambda l: l.args.get('X', float('inf'))).args['X']
		min_y = min(self.lines, key=lambda l: l.args.get('Y', float('inf'))).args['Y']
		max_x = max(self.lines, key=lambda l: l.args.get('X', float('-inf'))).args['X']
		max_y = max(self.lines, key=lambda l: l.args.get('Y', float('-inf'))).args['Y']
		return min_x, min_y, max_x, max_y


	def extents_gcode(self):
		"""Return two Lines of gcode that move to the extents."""
		min_x, min_y, max_x, max_y = self.extents()
		return Line(code='G0', args={'X': min_x, 'Y': min_y}),\
					 Line(code='G0', args={'X': max_x, 'Y': max_y})


	def z(self):
		"""Return the first Z height found for this layer. It should be
		the only Z unless it's been messed with, so returning the first is
		safe."""
		for l in self.lines:
			if 'Z' in l.args:
				return l.args['Z']


	def set_preamble(self, gcodestr):
		"""Insert lines of gcode at the beginning of the layer."""
		self.preamble = [Line(l) for l in gcodestr.split('\n')]


	def set_postamble(self, gcodestr):
		"""Add lines of gcode at the end of the layer."""
		self.postamble = [Line(l) for l in gcodestr.split('\n')]


	def find(self, code):
		"""Return all lines in this layer matching the given G code."""
		return [line for line in self.lines if line.code == code]


	def shift(self, **kwargs):
		"""Shift this layer by the given amount, applied to the given
		args. Operates by going through every line of gcode for this layer
		and adding amount to each given arg, if it exists, otherwise
		ignoring."""
		for line in self.lines:
			for arg in kwargs:
				if arg in line.args:
					line.args[arg] += kwargs[arg]

	def z_compensate(self, compensator):
		"""Shifts every XY move line in this layer by the amount specified by
		compensator(). compensator is a Compensator3D instance representing
		the error model being used for compensation."""
		for line in self.lines:
			if line.code in {'G1','G0'}:
				if 'X' in line.args and 'Y' in line.args: #check if it is an XY move line
					X = line.args['X']
					Y = line.args['Y']
					#apply z compensation with appropriate xy offset
					line.args['Z'] = line.args['Z'] -\
					 compensator.get_predicted_error(X-4.195,Y-28.195,self.z()) 
				elif 'X' in line.args or 'Y' in line.args: #uniaxial traverses
					line.args['Z'] = self.z() #force to original layer height
			#elif line.code == 'G0': #default G0 lines to original layer height
				#line.args['Z'] = self.z()

	def multiply(self, **kwargs):
		"""Same as shift but with multiplication instead."""
		for line in self.lines:
			for arg in kwargs:
				if arg in line.args:
					line.args[arg] *= kwargs[arg]


	def construct(self):
		"""Construct and return a gcode string."""
		return '\n'.join(l.construct() for l in self.preamble + self.lines
				+ self.postamble)

class Gcode(object):
	def __init__(self, filename=None, filestring=''):
		"""Parse a file's worth of gcode passed as a string. Example:
		  g = Gcode(open('mycode.gcode').read())"""
		self.preamble = None
		self.layers   = []
		if filename:
			if filestring:
				warnings.warn("Ignoring passed filestring in favor of loading file.")
			filestring = open(filename).read()
		self.parse(filestring)


	def __repr__(self):
		return '<Gcode with %d layers>' % len(self.layers)


	def construct(self, outfile=None):
		"""Construct all and return of the gcode. If outfile is given,
		write the gcode to the file instead of returning it."""
		s = (self.preamble.construct() + '\n') if self.preamble else ''
		for i,layer in enumerate(self.layers):
			s += ';LAYER:%d\n' % i
			s += layer.construct()
			s += '\n'
		if outfile:
			with open(outfile, 'w') as f:
				f.write(s)
		else:
			return s

	def shift(self, layernum=0, **kwargs):
		"""Shift given layer and all following. Provide arguments and
		amount as kwargs. Example: shift(17, X=-5) shifts layer 17 and all
		following by -5 in the X direction."""
		for layer in self.layers[layernum:]:
			layer.shift(**kwargs)

	def z_compensate(self, compensator):
		"""Apply 3D z compensation to all layers in this gcode object,
		according to amount specified by compensator.get_predicted_error()."""
		for layer in self.layers[1:]:
			layer.z_compensate(compensator)

	def multiply(self, layernum=0, **kwargs):
		"""The same as shift() but multiply the given argument by a
		factor."""
		for layer in self.layers[layernum:]:
			layer.multiply(**kwargs)

	def parse(self, filestring):
		"""Parse the gcode."""
		if not filestring:
			return

		in_preamble = True
		in_raft = True

		#Cura nicely adds a "LAYER" comment just before each layer
		if ';LAYER:' in filestring:
			#Split into layers
			splits = re.split(r'^;LAYER:\d+\n', filestring, flags=re.M)
			self.preamble = Layer(splits[0].split('\n'), layernum=0)
			self.layers = [Layer(l.split('\n'), layernum=i) for i,l in
					enumerate(splits[1:])]
	
		#Sliced with Slic3r, so no LAYER comments; we have to look for
		# G0 or G1 commands with a Z in them
		else:
			layernum = 1
			curr_layer = []
			for l in filestring.split('\n'):
				if not l: #skip empty lines
					continue
				#Looks like a layer change because we have a Z
				if re.match(r'G[01]\s+Z-?\.?\d+', l): 
					if in_preamble:
						if not in_raft:
							self.preamble = Layer(
							Point(0,0,0), 
							curr_layer, 
							split=False, 
							layernum=0, 
							explicit=False) #do not split preamble (not compensating anyway)
							in_preamble = False #preamble ends at 1st layer change after raft end
						else:
							curr_layer.append(l) #append to preamble if still in raft
							continue #skip rest of loop
					else:
						if len(self.layers) == 0:
							self.layers.append(Layer(
								self.preamble.get_final_point(), 
								curr_layer, 
								layernum=layernum))
						else:
							self.layers.append(Layer(
								self.layers[-1].get_final_point(),
								curr_layer, 
								layernum=layernum))
						layernum =+ 1
					curr_layer = [l]

				#Not a layer change so add it to the current layer
				else:
					curr_layer.append(l)
					if l == '; END RAFT':
						in_raft = False # exit raft once END RAFT flag detected

			self.layers.append(Layer(
				self.layers[-1].get_final_point(), 
				curr_layer, 
				layernum=layernum))

if __name__ == "__main__":
	if sys.argv[1:]:
		g = Gcode(sys.argv[1])
		print g
		print g.layers
