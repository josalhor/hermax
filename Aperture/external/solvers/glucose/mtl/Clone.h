#ifndef Glucose_Clone_h
#define Glucose_Clone_h

namespace ApertureGlucose {

class Clone {
 public:
  virtual Clone* clone() const = 0;
};
};  // namespace ApertureGlucose

#endif