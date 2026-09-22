"""
Utility functions for CertiGen
"""

from PIL import Image


def find_coordinates(template_path: str):
    """
    Interactive tool to find coordinates for text placement.
    Opens the image and lets you click to get coordinates.
    
    Args:
        template_path: Path to template image
        
    Returns:
        Tuple of (x, y) coordinates or None
    """
    import matplotlib.pyplot as plt
    
    img = Image.open(template_path)
    fig, ax = plt.subplots(figsize=(12, 8))
    ax.imshow(img)
    ax.set_title("Click on the CENTER of where the name should go\nClose window when done")
    
    coords = []
    
    def onclick(event):
        if event.xdata and event.ydata:
            x, y = int(event.xdata), int(event.ydata)
            coords.append((x, y))
            print(f"Clicked: ({x}, {y})")
            ax.plot(x, y, 'r+', markersize=20, markeredgewidth=3)
            fig.canvas.draw()
    
    fig.canvas.mpl_connect('button_press_event', onclick)
    plt.show()
    
    if coords:
        print(f"\n📍 Use: manual_position={coords[-1]}")
    return coords[-1] if coords else None
