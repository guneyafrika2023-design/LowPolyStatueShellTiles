# LowPolyStatueShellTiles

Fusion360 Python script to produce the external tiles for a low-poly statue.
Each tile has a certain top-shape (external surface) and the bottom shape (internal surface of the shell-to be glued on the internal skeleton)

Input:
A 3D solid model in a low-poly shape, with its inside hollowed out by the SHELL feature. The shell thickness should be equal to the thickness of the tile material.
The script expects the model to be as part of the root component.

Output:
A set of individual DXF files showing:
  1. Tile index number
  2. Tile laser cut boundaries (mirrored) - these boundaries will be the external boundaries between tiles
  3. Tile bottom boundaries (mirrored) - these boundaries will not be cut but will be burned on the tile bottom. Once a tile is cut, the tile bottom is filed into the shape of these boundaries and will be glued on the internal skeleton.

