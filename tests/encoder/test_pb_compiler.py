import unittest
from unittest.mock import patch, MagicMock
from hermax.encoder import PBCompiler, PBItem
from hermax.encoder.pbamo import PBAMOEnc
from hermax.internal.kmerge import KMergeConfig, PBConstraintStub

class TestPBEagerLearning(unittest.TestCase):
    def test_eager_amo_learning(self):
        """
        Scenario:
        1. C1 is an AMO: x1 + x2 + x3 <= 1
        2. C2 is a weighted PB overlapping with C1: 10*x1 + 10x2 + 10x3 + 5*y <= 25
        
        Expectation:
        When compiling C2, the PBCompiler should ALREADY know that {x1, x2, x3} is an AMO,
        even if it wasn't in the global groups initially.
        """
        items = [
            PBItem(
                lits=[1, 2, 3],
                bound=1,
                cmp_op="<=",
                weights=None  # Implicit cardinality
            ),
            PBItem(
                lits=[1, 2, 3, 4],
                weights=[10, 10, 10, 5],
                bound=25,
                cmp_op="<="
            )
        ]
        
        global_amo = [] # Empty initially
        global_eo = []
        top_id = 10
        
        # We patch auto_leq and partition_constraints where they are USED by PBCompiler
        with patch("hermax.encoder.pb.PBAMOEnc.auto_leq") as mock_leq, \
             patch("hermax.encoder.pb.partition_constraints") as mock_partition:
            
            # Force partitioner to return singletons (disabling K-MERGE for this test)
            mock_partition.return_value = [[0], [1]]
            
            mock_cnf = MagicMock()
            mock_cnf.nv = top_id
            mock_cnf.clauses = []
            mock_leq.return_value = mock_cnf
            
            PBCompiler.compile_batch(items, global_amo, global_eo, top_id)
            
            # Check calls
            self.assertEqual(mock_leq.call_count, 2)
            
            # Call 1: The AMO itself
            # call1_args = mock_leq.call_args_list[0]
            # Call 2: The weighted PB
            call2_kwargs = mock_leq.call_args_list[1].kwargs
            
            # EAGER LEARNING CHECK:
            # The second call should have {1, 2, 3} in its amo_groups
            passed_amo_groups = call2_kwargs.get("amo_groups", [])
            
            amo_found = False
            for group in passed_amo_groups:
                if set(group) == {1, 2, 3}:
                    amo_found = True
                    break
            
            self.assertTrue(amo_found, "The weighted PB was compiled without knowledge of the previous AMO in the same batch!")

    def test_kmerge_config_is_forwarded_to_partition_and_encoder(self):
        items = [
            PBItem(lits=[1, 2, 3], weights=[10, 10, 10], bound=15, cmp_op="<="),
            PBItem(lits=[1, 2, 4], weights=[6, 6, 6], bound=9, cmp_op="<="),
        ]
        config = KMergeConfig(
            basis_mode="bitplane",
            use_delay_cost=True,
            use_slack_tripwire=True,
            min_mean_term_len_for_merge=0.0,
        )

        with patch("hermax.encoder.pb.partition_constraints") as mock_partition, \
             patch("hermax.encoder.pb.PBAMOEnc.multi_leq") as mock_multi:
            mock_partition.return_value = [[0, 1]]
            mock_cnf = MagicMock()
            mock_cnf.nv = 10
            mock_cnf.clauses = []
            mock_multi.return_value = mock_cnf

            PBCompiler.compile_batch_with_options(
                items=items,
                amo_groups=[],
                eo_groups=[],
                top_id=10,
                merge_pb_optimization=True,
                kmerge_config=config,
            )

            self.assertEqual(mock_partition.call_args.kwargs["config"], config)
            self.assertEqual(mock_multi.call_args.kwargs["kmerge_config"], config)

    def test_hybrid_kmerge_resolves_cluster_config_before_partition_and_encode(self):
        items = [
            PBItem(lits=[1, 2, 3], weights=[10, 10, 10], bound=16, cmp_op="<="),
            PBItem(lits=[1, 2, 3], weights=[6, 6, 6], bound=12, cmp_op="<="),
            PBItem(lits=[1, 2, 3], weights=[4, 4, 4], bound=8, cmp_op="<="),
        ]
        config = KMergeConfig(
            routing_mode="hybrid",
            selector_bitplane_min_weight=8,
            selector_non_power_two_ratio_min=0.5,
            min_mean_term_len_for_merge=0.0,
        )

        with patch("hermax.encoder.pb.partition_constraints") as mock_partition, \
             patch("hermax.encoder.pb.PBAMOEnc.multi_leq") as mock_multi:
            mock_partition.return_value = [[0, 1, 2]]
            mock_cnf = MagicMock()
            mock_cnf.nv = 10
            mock_cnf.clauses = []
            mock_multi.return_value = mock_cnf

            PBCompiler.compile_batch_with_options(
                items=items,
                amo_groups=[],
                eo_groups=[],
                top_id=10,
                merge_pb_optimization=True,
                kmerge_config=config,
            )

            self.assertEqual(mock_partition.call_args.kwargs["config"].basis_mode, "bitplane")
            self.assertEqual(mock_multi.call_args.kwargs["kmerge_config"].basis_mode, "bitplane")

    def test_multi_leq_emits_short_circuit_clauses_for_shallow_conflicts(self):
        config = KMergeConfig(
            use_slack_tripwire=True,
            use_short_circuit_penalty=True,
            slack_conflict_depth_abort=4,
        )
        cnf = PBAMOEnc.multi_leq(
            lits=(1, 2, 3, 4, 5),
            stubs=[
                PBConstraintStub(lits=(1, 2, 3, 4, 5), weights=(4, 3, 3, 2, 0), bound=5, op="<="),
                PBConstraintStub(lits=(1, 2, 3, 4, 5), weights=(4, 3, 3, 2, 5), bound=12, op="<="),
            ],
            top_id=5,
            kmerge_config=config,
        )
        for clause in ([-1, -2], [-1, -3], [-1, -4], [-2, -3]):
            self.assertIn(clause, cnf.clauses)

if __name__ == "__main__":
    unittest.main()
