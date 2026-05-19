import ROOT
from halld_refit import Refitter

"""
An example for swapping pions to kaons in a pi+pi- tree
"""


refitter = Refitter(
    halld_path="../../../",
    in_file_path="your_file.root",
    tree_name="pippim__B4_Tree",
    mag_field_coarse="path/to/magneticField/field_map_coarseMesh_111861.msgpack",
    mag_field_fine="path/to/magneticField/field_map_fineMesh_111861.msgpack"
)

# try fitting all pions as kaons
refitter.add_hypothesis(
    name="pippim",
    swaps={
        ROOT.PiPlus: ROOT.KPlus,
        ROOT.PiMinus: ROOT.KMinus
    }
)

stats = refitter.process_events(
    out_file_path="outfile.root",
    max_events=1000
)

print(stats)