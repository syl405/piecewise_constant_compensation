import re, sys, warnings

class Line(object):
	def __init__(self, line='', code=None, args={}, comment=None):
		"""Parse a single line of gcode into its code and named
		arguments."""
		self.line    = line
		self.code    = code
		self.args    = args
		self.comment = comment

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
									self.args[arg[0]] = float(arg[1:]) if '.' in arg[1:] else int(arg[1:]) #only convert to float if decimal point present
								except ValueError:
									sys.stderr.write("Line: %s\n" % line)
									sys.stderr.write("Code: %s\n" % self.code)
									sys.stderr.write("args: %s\n" % args)
									raise
							else:
								self.args[arg[0]] = None
						else:
							self.args[None] = arg


	def __repr__(self):
		return self.construct()
		return '%s: %s' % (self.code, repr(self.args))


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
	def __init__(self, lines=[], layernum=None):
		"""Parse a layer of gcode line-by-line, making Line objects."""
		self.layernum  = layernum
		self.preamble  = []
		self.lines     = [Line(l) for l in lines if l]
		self.postamble = []


	def __repr__(self):
		return '<Layer %s at Z=%s; corners: (%d, %d), (%d, %d); %d lines>' % (
				(self.layernum, self.z()) + self.extents() + (len(self.lines),))


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
			if line.code == 'G1': #apply compensation only to G1 lines (Slic3r generated lines)
				if 'X' in line.args and 'Y' in line.args: #check if it is an XY move line
					X = line.args['X']
					Y = line.args['Y']
					line.args['Z'] = self.z() - compensator.get_predicted_error(X,Y,self.z()) #apply z compensation
				elif 'X' in line.args or 'Y' in line.args: #uniaxial traverses (theses are non-print moves)
					line.args['Z'] = self.z() #force to original layer height
			elif line.code == 'G0': #default G0 lines to original layer height
				line.args['Z'] = self.z()

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
			#s += ';LAYER:%d\n' % i
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
		for layer in self.layers:
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

				#Looks like a layer change because we have a Z
				if re.match(r'G[01]\s+Z-?\.?\d+', l): #this may pose problems when we try to do non-planar layers (e.g. volumeteric error compensation)
					if in_preamble:
						self.preamble = Layer(curr_layer, layernum=0)
						in_preamble = False
					else:
						self.layers.append(Layer(curr_layer, layernum=layernum))
						layernum =+ 1
					curr_layer = [l]

				#Not a layer change so add it to the current layer
				else:
					curr_layer.append(l)

			self.layers.append(Layer(curr_layer))


if __name__ == "__main__":
	if sys.argv[1:]:
		g = Gcode(sys.argv[1])
		print g
		print g.layers
