#pragma once

#include <zlib.h>

#include <fstream>
#include <string>

namespace Aperture {

static const int kChunkSize = 1048576;  // 1MB buffer

class CNFReader {
 public:
  explicit CNFReader(const std::string& path);
  ~CNFReader();

  int operator*() const {
    return (buffer_index_ >= size_) ? EOF : buffer_[buffer_index_];
  }
  void operator++() {
    buffer_index_++;
    CheckIfShouldLoadNextChunk();
  }

  size_t GetFileSize() const { return file_size_; }

 private:
  bool is_compressed_;
  gzFile gz_file_;
  std::ifstream file_;
  size_t file_size_;
  unsigned char buffer_[kChunkSize];
  int buffer_index_;
  int size_;

  inline void CheckIfShouldLoadNextChunk() {
    if (buffer_index_ >= size_) LoadNextChunk();
  }

  void LoadNextChunk();
};
};  // namespace Aperture