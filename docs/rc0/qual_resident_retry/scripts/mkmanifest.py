import json, sys
fam, dst = sys.argv[1], sys.argv[2]
M = {"e10641": (["Movies/HM70-1_10-A-002_0002_Oct28_23.00.41.tif", "Movies/HM70-1_10-A-004_0008_Oct28_23.06.04.tif"], [5760, 4092, 1]),
     "e10216": (["Movies/FoilHole_14961495_Data_14966722_14966723_20180615_1739_Fractions.mrcs", "Movies/FoilHole_14961496_Data_14966722_14966723_20180615_1742_Fractions.mrcs"], [4096, 4096, 1]),
     "tutorial": (["Movies/20170629_00026_frameImage.tiff", "Movies/20170629_00031_frameImage.tiff"], [3710, 3838, 1])}[fam]
json.dump({"schema_version": 1, "expected_shape_xyz": M[1], "joint_star": "corrected_micrographs.star", "movies": M[0]}, open(dst, "w"), indent=1)
