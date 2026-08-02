// ~Aperture

#include <string.h>

#include "internal.h"
#include "polarities.h"
#include "require.h"
#include "logging.h"

#define realloc_polarities() \
  do { \
    solver->polarities = \
        kissat_realloc (solver, solver->polarities, old_size, new_size); \
  } while (0)

#define increase_polarities() \
  do { \
    assert (old_size < new_size); \
    realloc_polarities (); \
    memset (solver->polarities + old_size, 0, new_size - old_size); \
  } while (0)


void kissat_increase_polarities (kissat *solver, unsigned new_size) {
  const unsigned old_size = solver->size;
  assert (old_size < new_size);
  LOG ("increasing polarities from %u to %u", old_size, new_size);
  increase_polarities ();
}

void kissat_decrease_polarities (kissat *solver, unsigned new_size) {
  const unsigned old_size = solver->size;
  assert (old_size > new_size);
  LOG ("decreasing polarities from %u to %u", old_size, new_size);
  realloc_polarities ();
} 

void kissat_release_polarities (kissat *solver) {
  const unsigned size = solver->size;
  kissat_free (solver, solver->polarities, size);
}