"""
Pseudocode:

- Open gcode file
- Read header into memory
- Save any parameters necessary for subsequent operations
- Clear header from memory
- Read lines until layer change detected
- Calculate predicted height error for this layer
- Add predicted height error to pending uncompensated height error
- Check whether pending uncompensated height error exceeds half of Z-step resolution
	- If yes, adjust thickness of current layer to closest Z-step and decrement pending uncompensated height error by compensation applied
		- For each move in the current layer:
			- Calculate extrusion amount adjustment needed to maintain extrusion width for each move
			- Apply extrusion amount adjustment
		- loop back to "Read lines until layer change detected"
	- If no, loop back to "Read lines until layer change detected"
"""