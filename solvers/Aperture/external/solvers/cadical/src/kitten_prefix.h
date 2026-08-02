#ifndef _kitten_prefix_h_INCLUDED
#define _kitten_prefix_h_INCLUDED

// Rename all kitten symbols to cadical_kitten_* to avoid link-time conflicts
// with Kissat, which ships its own copy of kitten with identical symbol names.

#define kitten_init                                cadical_kitten_init
#define kitten_clear                               cadical_kitten_clear
#define kitten_release                             cadical_kitten_release

#ifdef LOGGING
#define kitten_set_logging                         cadical_kitten_set_logging
#endif

#define kitten_track_antecedents                   cadical_kitten_track_antecedents

#define kitten_shuffle_clauses                     cadical_kitten_shuffle_clauses
#define kitten_flip_phases                         cadical_kitten_flip_phases
#define kitten_randomize_phases                    cadical_kitten_randomize_phases

#define kitten_no_ticks_limit                      cadical_kitten_no_ticks_limit
#define kitten_set_ticks_limit                     cadical_kitten_set_ticks_limit
#define kitten_current_ticks                       cadical_kitten_current_ticks

#define kitten_no_terminator                       cadical_kitten_no_terminator
#define kitten_set_terminator                      cadical_kitten_set_terminator

#define kitten_assume                              cadical_kitten_assume
#define kitten_assume_signed                       cadical_kitten_assume_signed

#define kitten_clause                              cadical_kitten_clause
#define kitten_unit                                cadical_kitten_unit
#define kitten_binary                              cadical_kitten_binary
#define kitten_clause_with_id_and_exception        cadical_kitten_clause_with_id_and_exception

#define kitten_solve                               cadical_kitten_solve
#define kitten_status                              cadical_kitten_status

#define kitten_value                               cadical_kitten_value
#define kitten_signed_value                        cadical_kitten_signed_value
#define kitten_fixed                               cadical_kitten_fixed
#define kitten_fixed_signed                        cadical_kitten_fixed_signed
#define kitten_failed                              cadical_kitten_failed
#define kitten_flip_literal                        cadical_kitten_flip_literal
#define kitten_flip_signed_literal                 cadical_kitten_flip_signed_literal

#define kitten_compute_clausal_core                cadical_kitten_compute_clausal_core
#define kitten_shrink_to_clausal_core              cadical_kitten_shrink_to_clausal_core
#define kitten_traverse_core_ids                   cadical_kitten_traverse_core_ids
#define kitten_traverse_core_clauses               cadical_kitten_traverse_core_clauses
#define kitten_traverse_core_clauses_with_id       cadical_kitten_traverse_core_clauses_with_id
#define kitten_trace_core                          cadical_kitten_trace_core

#define kitten_compute_prime_implicant             cadical_kitten_compute_prime_implicant
#define kitten_add_prime_implicant                 cadical_kitten_add_prime_implicant
#define kitten_flip_and_implicant_for_signed_literal cadical_kitten_flip_and_implicant_for_signed_literal

// Non-header internal symbols that are globally visible and conflict
#define new_learned_klause                         cadical_new_learned_klause
#define completely_backtrack_to_root_level         cadical_completely_backtrack_to_root_level

#endif