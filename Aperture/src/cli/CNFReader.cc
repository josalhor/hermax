#include "CNFReader.h"

#include <sys/stat.h>

#include <cassert>
#include <stdexcept>

using namespace std;
using namespace Aperture;

CNFReader::CNFReader(const string& path)
    : is_compressed_(path.ends_with(".gz")),
      gz_file_(nullptr),
      file_size_(0),
      buffer_index_(0),
      size_(0) {
  if (is_compressed_) {
    gz_file_ = gzopen(path.c_str(), "rb");
    if (gz_file_ == nullptr) {
      throw runtime_error("Failed to open gzipped file: " + path);
    }
    struct stat st;
    if (stat(path.c_str(), &st) == 0) {
      file_size_ = st.st_size * 4;
    }
  } else {
    file_.open(path, ios::in | ios::binary);
    if (!file_.is_open()) {
      throw runtime_error("Failed to open file: " + path);
    }
    file_.seekg(0, ios::end);
    file_size_ = file_.tellg();
    file_.seekg(0, ios::beg);
  }
  CheckIfShouldLoadNextChunk();
}

CNFReader::~CNFReader() {
  if (gz_file_) {
    gzclose(gz_file_);
  }
  if (file_.is_open()) {
    file_.close();
  }
}

void CNFReader::LoadNextChunk() {
  buffer_index_ = 0;
  if (is_compressed_) {
    int bytes_read = gzread(gz_file_, buffer_, kChunkSize);
    size_ = bytes_read > 0 ? bytes_read : 0;
  } else {
    file_.read(reinterpret_cast<char*>(buffer_), kChunkSize);
    size_ = static_cast<int>(file_.gcount());
  }
}