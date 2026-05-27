import ROOT
import array

class Refitter:
    def __init__(self, halld_path, in_file_path, tree_name, mag_field_coarse, mag_field_fine):
        """
        Initializes the Refitter by loading the appropriate C++ dependencies
        and extracting the tree's topology.
        """
        self.halld_path = halld_path
        self._init_pyroot(mag_field_coarse, mag_field_fine)
        
        self.in_file_path = in_file_path
        self.tree_name = tree_name

        # retrieve tree from provided file
        self.in_file = ROOT.TFile.Open(in_file_path, "READ")
        if not self.in_file or self.in_file.IsZombie():
            raise FileNotFoundError(f"Could not open ROOT file: {in_file_path}")
            
        self.in_tree = self.in_file.Get(tree_name)
        if not self.in_tree:
            raise ValueError(f"Tree '{tree_name}' not found in {in_file_path}")

        # get topology from UserInfo
        self.user_info = self._get_user_info()
        self.num_steps, self.combo_info_map = self._get_combo_info()
        self.beam, self.target = self._get_initial_target()
        self.detected_particles = self._get_detected()
        
        # init state
        self.hypotheses = []
        # upper limit for combos per event to size the branch buffer 
        self.MAX_COMBOS = 4000 
        
        # cache PDG constants
        self.pdg_type = {}
        self.p_charge = {}
        self.p_mass = {}
        for pt, pname in self.detected_particles + [self.beam, self.target]:
            self.pdg_type[pt] = ROOT.PDGtype(pt)
            self.p_charge[pt] = ROOT.ParticleCharge(pt)
            self.p_mass[pt] = ROOT.ParticleMass(pt)

    def _init_pyroot(self, mag_field_coarse, mag_field_fine):
        ROOT.gROOT.SetBatch(True)
        # add search paths for includes
        ROOT.gInterpreter.AddIncludePath("$JANA_HOME/include")
        ROOT.gInterpreter.AddIncludePath(f"{self.halld_path}/src/libraries")
        ROOT.gInterpreter.AddIncludePath(f"{self.halld_path}/src/libraries/include")
        ROOT.gInterpreter.AddIncludePath(f"{self.halld_path}/src/external")

        # set search paths for libraries
        ROOT.gSystem.AddDynamicPath("$JANA_HOME/lib")
        ROOT.gSystem.AddDynamicPath(f"{self.halld_path}/$BMS_OSNAME/lib")

        # load the shared library
        ROOT.gInterpreter.Declare("#define _KINFITTER_STANDALONE_")
        ROOT.gInterpreter.ProcessLine('#include "KINFITTER/DKinFitUtils_StandAlone.h"')
        ROOT.gInterpreter.ProcessLine(
            '#include "include/particleType.h"'
        )
        assert (
            ROOT.gSystem.Load("obj/libKINFITTER.so") >= 0
        ), "Could not load 'libKINFITTER.so'"

        # C++ helper for unpacking matrices
        if not hasattr(ROOT, "FastUnpackMatrix"):
            ROOT.gInterpreter.Declare("""
            #include "TMatrixFSym.h"
            void FastUnpackMatrix(const void* source_void, TMatrixFSym* dest, int dim, int offset) {
                const float* source = (const float*)source_void;
                int k = offset;
                for (int i = 0; i < dim; ++i) {
                    for (int j = i; j < dim; ++j) {
                        float val = source[k++];
                        (*dest)(i, j) = val;
                        (*dest)(j, i) = val;
                    }
                }
            }
            """)

        self.kinFitUtils = ROOT.DKinFitUtils_StandAlone(mag_field_coarse, mag_field_fine)
        self.kinFitter = ROOT.DKinFitter(self.kinFitUtils)

    def _get_user_info(self):
        if isinstance(self.in_tree, ROOT.TChain):
            return self.in_tree.GetTree().GetUserInfo()
        return self.in_tree.GetUserInfo()

    def _get_combo_info(self):
        locComboInfoMap = {}
        locNameToPIDMap = self.user_info.FindObject("NameToPIDMap")
        locPositionToNameMap = self.user_info.FindObject("PositionToNameMap")

        locMapIterator = ROOT.TMapIter(locPositionToNameMap)
        locKeyObjString = locMapIterator.Next()
        locNumSteps = 0

        while locKeyObjString:
            locLocationString = locKeyObjString.GetName()
            locStepString, locParticleString = locLocationString.split("_", 1)
            locStepIndex = int(locStepString)
            locParticleIndex = int(locParticleString)

            if locStepIndex >= locNumSteps:
                locNumSteps = locStepIndex + 1

            locValueObjString = locPositionToNameMap.GetValue(locKeyObjString)
            locParticleName = locValueObjString.GetName()

            locPIDObjString = locNameToPIDMap.GetValue(locParticleName)
            locPDGPID = int(locPIDObjString.GetName())
            locPID = ROOT.PDGtoPType(locPDGPID)

            if locStepIndex not in locComboInfoMap:
                locComboInfoMap[locStepIndex] = {}

            locComboInfoMap[locStepIndex][locParticleIndex] = (locPID, locParticleName)
            locKeyObjString = locMapIterator.Next()

        if 0 not in locComboInfoMap:
            locComboInfoMap[0] = {}

        if -2 not in locComboInfoMap[0]:
            locParticleNameList = self.user_info.FindObject("ParticleNameList")
            if locParticleNameList and locParticleNameList.FindObject("Target"):
                locComboInfoMap[0][-2] = (ROOT.Proton, "Target")

        return locNumSteps, locComboInfoMap

    def _get_initial_target(self):
        return self.combo_info_map[0][-1], self.combo_info_map[0][-2]

    def _get_detected(self):
        detected_particles = []
        if 0 not in self.combo_info_map:
            return detected_particles

        for particle_index, (particle_type, particle_name) in self.combo_info_map[0].items():
            if particle_index >= 0 and not particle_name.startswith("Missing"):
                detected_particles.append((particle_type, particle_name))

        return detected_particles

    def _enable_branches(self):
        self.in_tree.SetBranchStatus("*", 0) 
        
        needed_branches = [
            "NumCombos", "RunNumber", "EventNumber", "NumBeam",
            "NumChargedHypos", "NumNeutralHypos", "RFTime_Measured",
            "ComboBeam__BeamIndex", "ComboBeam__P4_KinFit", "ComboBeam__X4_KinFit", "ComboBeam__ErrMatrix",
            "Beam__P4_Measured", "Beam__X4_Measured",
            "ChargedHypo__P4_Measured", "ChargedHypo__X4_Measured",
            "NeutralHypo__P4_Measured", "NeutralHypo__X4_Measured",
            "ChiSq_KinFit", "NDF_KinFit", "IsComboCut"
        ]

        for pt, pname in self.detected_particles:
            needed_branches.extend([
                f"{pname}__ChargedIndex", f"{pname}__NeutralIndex",
                f"{pname}__P4_KinFit", f"{pname}__X4_KinFit",
                f"{pname}__Beta_Timing_Measured", f"{pname}__ChiSq_Timing_Measured",
                f"{pname}__ErrMatrix"
            ])

        for branch_name in needed_branches:
            if self.in_tree.GetBranch(branch_name):
                self.in_tree.SetBranchStatus(branch_name, 1)

    def add_hypothesis(self, name, swaps):
        """
        Adds an alternative particle hypothesis to test against the main hypothesis
        swaps is a dictionary mapping {original Particle_t: new Particle_t}
        """
        self.hypotheses.append({
            "name": name,
            "swaps": swaps
        })
        for pt in swaps.values():
            if pt not in self.pdg_type:
                self.pdg_type[pt] = ROOT.PDGtype(pt)
                self.p_charge[pt] = ROOT.ParticleCharge(pt)
                self.p_mass[pt] = ROOT.ParticleMass(pt)

    def process_events(self, out_file_path, max_events=None, output_mode="cut"):
        self._enable_branches()

        # disable IsComboCut during the clone so we can create a clean mutable buffer in the new tree
        if self.in_tree.GetBranch("IsComboCut"):
            self.in_tree.SetBranchStatus("IsComboCut", 0)

        out_file = ROOT.TFile.Open(out_file_path, "RECREATE")
        out_tree = self.in_tree.CloneTree(0)
        
        # link out_tree to in_tree buffers to avoid access conflicts and memory corruption
        self.in_tree.CopyAddresses(out_tree)

        # re-enable original IsComboCut to read its current state
        if self.in_tree.GetBranch("IsComboCut"):
            self.in_tree.SetBranchStatus("IsComboCut", 1)

        # prepare python array buffer for the new IsComboCut branch
        is_combo_cut_buf = array.array('B', [0] * self.MAX_COMBOS)
        out_tree.Branch("IsComboCut", is_combo_cut_buf, f"IsComboCut[NumCombos]/O")

        # prepare buffers for chisq branches if requested
        chisq_bufs = {}
        if output_mode == "chisq":
            for hypo in self.hypotheses:
                name = hypo["name"]
                buf = array.array('f', [0.0] * self.MAX_COMBOS)
                chisq_bufs[name] = buf
                out_tree.Branch(f"{name}_chisq_ndf", buf, f"{name}_chisq_ndf[NumCombos]/F")

        processed = 0
        combos_cut_total = 0
        
        num_entries = self.in_tree.GetEntries()
        if max_events is not None:
            num_entries = min(num_entries, max_events)

        # pre-allocate resources for the entire run
        shared_mats = {self.beam[0]: ROOT.std.make_shared[ROOT.TMatrixFSym](7)}
        for pt, pname in self.detected_particles:
            shared_mats[pt] = ROOT.std.make_shared[ROOT.TMatrixFSym](7)

        target_part = self.kinFitUtils.Make_TargetParticle(
            self.pdg_type[self.target[0]],
            self.p_charge[self.target[0]],
            self.p_mass[self.target[0]]
        )
        
        dummy_x4 = ROOT.TLorentzVector()
        dummy_p3 = ROOT.TVector3()
        beam_part = self.kinFitUtils.Make_BeamParticle(
            self.pdg_type[self.beam[0]],
            self.p_charge[self.beam[0]],
            self.p_mass[self.beam[0]],
            dummy_x4,
            dummy_p3,
            shared_mats[self.beam[0]]
        )

        detected_parts = {}
        for pt, pname in self.detected_particles:
            detected_parts[pt] = self.kinFitUtils.Make_DetectedParticle(
                self.pdg_type[pt],
                self.p_charge[pt],
                self.p_mass[pt],
                dummy_x4,
                dummy_p3,
                1.0, # path length dummy
                shared_mats[pt]
            )

        initial_set = ROOT.std.set[ROOT.std.shared_ptr[ROOT.DKinFitParticle]]()
        final_set = ROOT.std.set[ROOT.std.shared_ptr[ROOT.DKinFitParticle]]()
        vtx_parts_set = ROOT.std.set[ROOT.std.shared_ptr[ROOT.DKinFitParticle]]()
        no_vtx_set = ROOT.std.set[ROOT.std.shared_ptr[ROOT.DKinFitParticle]]()

        initial_set.insert(target_part)
        initial_set.insert(beam_part)
        no_vtx_set.insert(target_part)
        no_vtx_set.insert(beam_part)

        for pt, part in detected_parts.items():
            final_set.insert(part)
            vtx_parts_set.insert(part)
            
        p4_const = self.kinFitUtils.Make_P4Constraint(initial_set, final_set)
        vtx_const = self.kinFitUtils.Make_VertexConstraint(vtx_parts_set, no_vtx_set, dummy_p3)

        for entry_idx in range(num_entries):
            self.in_tree.GetEntry(entry_idx)
            event = self.in_tree

            self.kinFitter.Reset_NewEvent()
            
            num_combos = event.NumCombos
            if num_combos > self.MAX_COMBOS:
                raise RuntimeError(f"Event combo count ({num_combos}) exceeds MAX_COMBOS ({self.MAX_COMBOS})")

            # hydrate output buffer with original states (if branch existed)
            has_existing_cut = hasattr(event, "IsComboCut")
            for combo_idx in range(num_combos):
                is_combo_cut_buf[combo_idx] = event.IsComboCut[combo_idx] if has_existing_cut else 0
                if output_mode == "chisq":
                    for name in chisq_bufs:
                        chisq_bufs[name][combo_idx] = -1.0

            for combo_idx in range(num_combos):
                if is_combo_cut_buf[combo_idx]:
                    continue

                orig_chisq = event.ChiSq_KinFit[combo_idx]
                orig_ndf = event.NDF_KinFit[combo_idx]
                
                if orig_ndf <= 0:
                    is_combo_cut_buf[combo_idx] = 1
                    combos_cut_total += 1
                    continue
                    
                orig_chisq_ndf = orig_chisq / orig_ndf

                beam_idx = int(event.ComboBeam__BeamIndex[combo_idx])
                
                b_beam_x4 = event.Beam__X4_Measured
                ROOT.SetOwnership(b_beam_x4, False)
                beam_x4_obj = b_beam_x4.At(beam_idx)
                
                b_beam_p4 = event.Beam__P4_Measured
                ROOT.SetOwnership(b_beam_p4, False)
                beam_p4_obj = b_beam_p4.At(beam_idx)
                
                ROOT.FastUnpackMatrix(event.ComboBeam__ErrMatrix, shared_mats[self.beam[0]], 7, 0)
                
                beam_part.Set_SpacetimeVertex(beam_x4_obj)
                beam_part.Set_Momentum(beam_p4_obj.Vect())

                vtx_const.Set_InitVertexGuess(beam_x4_obj.Vect())

                for pt, pname in self.detected_particles:
                    if self.p_charge[pt] != 0:
                        idx_view = getattr(event, f"{pname}__ChargedIndex")
                        p4_br = event.ChargedHypo__P4_Measured
                        x4_br = event.ChargedHypo__X4_Measured
                    else:
                        idx_view = getattr(event, f"{pname}__NeutralIndex")
                        p4_br = event.NeutralHypo__P4_Measured
                        x4_br = event.NeutralHypo__X4_Measured
                    
                    ROOT.SetOwnership(p4_br, False)
                    ROOT.SetOwnership(x4_br, False)
                    
                    idx = int(idx_view[combo_idx])
                    ROOT.FastUnpackMatrix(getattr(event, f"{pname}__ErrMatrix"), shared_mats[pt], 7, 0)
                    
                    det_p4_obj = p4_br.At(idx)
                    det_x4_obj = x4_br.At(idx)
                        
                    part = detected_parts[pt]
                    part.Set_SpacetimeVertex(det_x4_obj)
                    part.Set_Momentum(det_p4_obj.Vect())

                for hypothesis in self.hypotheses:
                    swaps = hypothesis["swaps"]
                    
                    for pt, part in detected_parts.items():
                        eval_pt = swaps.get(pt, pt)
                        if eval_pt != pt:
                            part.Set_PID(self.pdg_type[eval_pt])
                            part.Set_Charge(self.p_charge[eval_pt])
                            part.Set_Mass(self.p_mass[eval_pt])

                    self.kinFitter.Reset_NewFit()
                    self.kinFitter.Add_Constraint(p4_const)
                    self.kinFitter.Add_Constraint(vtx_const)
                    
                    fit_status = self.kinFitter.Fit_Reaction()
                    
                    # reset hypothesis back to original
                    for pt, part in detected_parts.items():
                        eval_pt = swaps.get(pt, pt)
                        if eval_pt != pt:
                            part.Set_PID(self.pdg_type[pt])
                            part.Set_Charge(self.p_charge[pt])
                            part.Set_Mass(self.p_mass[pt])

                    if fit_status: 
                        new_ndf = self.kinFitter.Get_NDF()
                        if new_ndf > 0:
                            new_chisq_ndf = self.kinFitter.Get_ChiSq() / new_ndf
                            
                            if output_mode == "chisq":
                                chisq_bufs[hypothesis["name"]][combo_idx] = new_chisq_ndf
                            elif output_mode == "cut":
                                if new_chisq_ndf < orig_chisq_ndf:
                                    is_combo_cut_buf[combo_idx] = 1
                                    combos_cut_total += 1
                                    break 

            out_tree.Fill()
            processed += 1

        out_tree.Write()
        out_file.Close()
        self.in_file.Close()

        return {
            "events_processed": processed,
            "combos_cut_by_refit": combos_cut_total
        }
