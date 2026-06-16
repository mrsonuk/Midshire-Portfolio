"""Official NHS identity palette (nhsengland.github.io/nhs-r-reporting nhs-colours)."""
NHS_DARK = "#003087"
NHS_BLUE = "#005EB8"
NHS_BRIGHT = "#0072CE"
NHS_AQUA = "#00A9CE"
NHS_LIGHT = "#41B6E6"
NHS_GREEN = "#009639"
NHS_YELLOW = "#FFB81C"
NHS_ORANGE = "#ED8B00"
NHS_RED = "#DA291C"
NHS_GREY = "#425563"
NHS_BLACK = "#231F20"
NHS_LIGHTGREY = "#E8EDEE"

SERIES = [NHS_BRIGHT, NHS_AQUA, NHS_LIGHT, NHS_YELLOW, NHS_ORANGE, NHS_GREY,
          "#8A1538", "#330072", "#78BE20"]

LAYOUT = dict(
    paper_bgcolor="white", plot_bgcolor="white",
    font=dict(family="Frutiger, Arial, sans-serif", color=NHS_BLACK, size=12),
    margin=dict(l=55, r=20, t=50, b=45),
    title=dict(font=dict(color=NHS_DARK, size=15)),
)
