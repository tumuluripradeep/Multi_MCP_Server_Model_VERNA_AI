"""
Simple script to generate placeholder icons for the Chrome extension.
Run this to create basic icon files for development.
"""

import os
from PIL import Image, ImageDraw, ImageFont

def create_icon(size, filename):
    """Create a simple icon with the MCP logo"""
    # Create a new image with a gradient background
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Draw gradient background
    for i in range(size):
        # Create gradient from purple to blue
        r = int(102 + (118 - 102) * i / size)  # 102 -> 118
        g = int(126 + (186 - 126) * i / size)  # 126 -> 186
        b = int(234 + (162 - 234) * i / size)  # 234 -> 162
        
        draw.line([(0, i), (size, i)], fill=(r, g, b, 255))
    
    # Draw robot emoji or text
    if size >= 32:
        try:
            # Try to load a font
            font = ImageFont.truetype("arial.ttf", size // 2)
        except:
            try:
                font = ImageFont.load_default()
            except:
                font = None
        
        # Draw robot emoji or "AI" text
        if font:
            text = "🤖" if size >= 48 else "AI"
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            
            x = (size - text_width) // 2
            y = (size - text_height) // 2
            
            draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))
        else:
            # Draw simple circle if no font available
            circle_size = size // 3
            x = (size - circle_size) // 2
            y = (size - circle_size) // 2
            draw.ellipse([x, y, x + circle_size, y + circle_size], 
                        fill=(255, 255, 255, 255))
    else:
        # For small icons, just draw a circle
        circle_size = size // 2
        x = (size - circle_size) // 2
        y = (size - circle_size) // 2
        draw.ellipse([x, y, x + circle_size, y + circle_size], 
                    fill=(255, 255, 255, 255))
    
    # Save the icon
    icons_dir = os.path.join(os.path.dirname(__file__), 'icons')
    os.makedirs(icons_dir, exist_ok=True)
    
    filepath = os.path.join(icons_dir, filename)
    img.save(filepath, 'PNG')
    print(f"Created icon: {filepath}")

def main():
    """Generate all required icon sizes"""
    print("Generating Chrome extension icons...")
    
    # Create icons for all required sizes
    sizes = [
        (16, 'icon16.png'),
        (32, 'icon32.png'),
        (48, 'icon48.png'),
        (128, 'icon128.png')
    ]
    
    for size, filename in sizes:
        create_icon(size, filename)
    
    print("Icon generation complete!")
    print("\nTo use custom icons:")
    print("1. Replace the generated PNG files in the icons/ directory")
    print("2. Ensure they are the correct sizes (16x16, 32x32, 48x48, 128x128)")
    print("3. Reload the extension in Chrome")

if __name__ == "__main__":
    try:
        main()
    except ImportError:
        print("PIL (Pillow) is required to generate icons.")
        print("Install it with: pip install Pillow")
        print("\nAlternatively, you can manually create PNG files:")
        print("- icons/icon16.png (16x16 pixels)")
        print("- icons/icon32.png (32x32 pixels)")
        print("- icons/icon48.png (48x48 pixels)")
        print("- icons/icon128.png (128x128 pixels)")
    except Exception as e:
        print(f"Error generating icons: {e}")
        print("You can manually create the required icon files in the icons/ directory.") 