"""Design tokens — colors, spacing, and typography for the TUI."""

# Colors (Flexoki-inspired dark theme)
BG = "#1e1e2e"           # Main background
BG_DARK = "#11111b"       # Darker background
BG_SURFACE = "#181825"    # Surface background
BG_INPUT = "#1e1e2e"      # Input field background

FG = "#cdd6f4"            # Main foreground
FG_DIM = "#6c7086"        # Dimmed text
FG_SUBTLE = "#a6adc8"     # Subtle text

ACCENT = "#89b4fa"        # Blue accent
GREEN = "#a6e3a1"         # Success/green
RED = "#f38ba8"           # Error/red
YELLOW = "#f9e2af"        # Warning/yellow
ORANGE = "#fab387"        # Orange
MAUVE = "#cba6f7"         # Purple
TEAL = "#94e2d5"          # Teal
PINK = "#f5c2e7"          # Pink
LAVENDER = "#b4befe"      # Lavender

# Tool colors (for tool call display)
TOOL_COLORS = {
    "read_file": ACCENT,
    "write_file": GREEN,
    "edit_file": YELLOW,
    "bash_command": ORANGE,
    "glob_pattern": TEAL,
    "search_files": LAVENDER,
    "list_directory": FG_SUBTLE,
    "web_fetch": MAUVE,
    "web_search": MAUVE,
    "git_status": ACCENT,
    "git_diff": TEAL,
    "git_commit": GREEN,
}

# Spacing
PADDING_X = 2
PADDING_Y = 1
SPACING_SM = 1
SPACING_MD = 2

# Typography
BOLD = "bold"
DIM = "dim"
ITALIC = "italic"