import os
import sys

# This utility converts a static PNG/JPG of the Results screen into the GIF
# used by README as assets/gifs/results_rankings.gif. It creates a 2s single-frame GIF.
# Usage:
#   python tools/make_results_gif.py [input_image_path]
# If input path is omitted, it defaults to assets/screenshots/results.png

def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    default_in = os.path.join(root, "assets", "screenshots", "results.png")
    input_path = sys.argv[1] if len(sys.argv) > 1 else default_in
    output_path = os.path.join(root, "assets", "gifs", "results_rankings.gif")

    if not os.path.isfile(input_path):
        print(f"[make_results_gif] Input image not found: {input_path}")
        print("Please place the screenshot (PNG/JPG) and run again.")
        sys.exit(1)

    # Try Pillow first, fallback to imageio
    try:
        from PIL import Image
        with Image.open(input_path) as im:
            # Convert to palette mode suitable for GIF if needed
            if im.mode in ("RGBA", "LA"):
                # Remove alpha by flattening onto dark background similar to game bg
                bg = Image.new("RGB", im.size, (14, 18, 22))
                bg.paste(im, mask=im.split()[-1])
                im = bg
            elif im.mode != "RGB":
                im = im.convert("RGB")
            # Save a single-frame GIF with 2000ms duration, loop forever
            im.save(output_path, format="GIF", save_all=True, append_images=[], duration=2000, loop=0)
        print(f"[make_results_gif] Wrote: {output_path}")
        return
    except Exception as e:
        print(f"[make_results_gif] Pillow path failed: {e}")

    try:
        import imageio.v2 as imageio
        img = imageio.imread(input_path)
        imageio.mimsave(output_path, [img], duration=2.0)
        print(f"[make_results_gif] Wrote via imageio: {output_path}")
        return
    except Exception as e:
        print(f"[make_results_gif] imageio path failed: {e}")

    print("[make_results_gif] No suitable library found. Please install Pillow or imageio.")
    print("For example:\n  python -m pip install pillow\n  # or\n  python -m pip install imageio")
    sys.exit(2)

if __name__ == "__main__":
    main()
