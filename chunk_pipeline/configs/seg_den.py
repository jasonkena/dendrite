TASK = "seg_den"

GENERAL__ANISOTROPY = (30, 6, 6)
base = "/mmfs1/data/adhinart/dendrite/raw/"
# seg is missing for seg_den
H5 = {
    "raw": (f"{base}{TASK}_raw.h5", "main"),
    "spine": (f"{base}{TASK}_spine.h5", "main"),
    "seg": (f"{base}{TASK}_seg.h5", "main"),

}  # "seg": (f"{base}{TASK}_seg.h5", "main")}
