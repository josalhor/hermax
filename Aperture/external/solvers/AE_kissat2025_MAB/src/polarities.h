// ~Aperture
#ifndef _polarities_h_INCLUDED
#define _polarities_h_INCLUDED

void kissat_increase_polarities (struct kissat *, unsigned);
void kissat_decrease_polarities (struct kissat *, unsigned);

void kissat_release_polarities (struct kissat *);

#endif