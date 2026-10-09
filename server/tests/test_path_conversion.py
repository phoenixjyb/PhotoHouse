#!/usr/bin/env python3
"""
Test path conversion function
"""

def convert_path_for_wsl(windows_path):
    """Convert Windows path to WSL-accessible path"""
    # Normalize path separators to forward slashes
    normalized_path = windows_path.replace('\\', '/')
    
    # Convert E:/path to /mnt/e/path
    if normalized_path.startswith('E:/'):
        wsl_path = normalized_path.replace('E:/', '/mnt/e/')
        return wsl_path
    # Convert C:/path to /mnt/c/path  
    elif normalized_path.startswith('C:/'):
        wsl_path = normalized_path.replace('C:/', '/mnt/c/')
        return wsl_path
    # For other drives, follow same pattern
    elif ':' in normalized_path:
        drive_letter = normalized_path[0].lower()
        path_part = normalized_path[2:]
        return f'/mnt/{drive_letter}{path_part}'
    return windows_path

# Reserved synthetic examples; no workstation or family paths.
import unittest


class PathConversionTests(unittest.TestCase):
    def test_drive_and_separator_conversion(self):
        cases = (
            (r"E:/example\generated\image.jpg", "/mnt/e/example/generated/image.jpg"),
            (r"C:\Users\example-user\test.jpg", "/mnt/c/Users/example-user/test.jpg"),
            (r"D:\example\video.mp4", "/mnt/d/example/video.mp4"),
            ("relative/example.jpg", "relative/example.jpg"),
        )
        for original, expected in cases:
            with self.subTest(original=original):
                self.assertEqual(convert_path_for_wsl(original), expected)


if __name__ == '__main__':
    unittest.main()
