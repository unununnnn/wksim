// Native verification source for the ros1_bridge std::vector<bool> ROS1
// serialization fix (Task 22a/22b).
//
// This TU does NOT carry a copy of the serializer. The functions under test
// are extracted from the ACTUAL template at build time:
//
//   sed -n '/^\/\/ This version is for write$/,/^@\[for m in mapped_msgs\]@$/p' \
//     bridge_ws/src/ros1_bridge/resource/interface_factories.cpp.em \
//     | sed '/^@\[for m in mapped_msgs\]@$/d' > /tmp/stream_primitive_vector.inc
//
// (range starts at the generic write overload and ends before the empy
// mapped_msgs loop, so the inc holds exactly the generic trio plus the
// vector<bool> overloads, no empy markup). The inc is included below inside
// namespace ros1_bridge, so the bytes tested are the bytes the bridge build
// compiles. Compilation itself is the first assertion: the generic template
// is ill-formed for std::vector<bool> (proxy reference from front()), so a
// successful build proves overload resolution selects the bool path.
//
// Verified against /opt/ros/noetic/include/ros/serialization.h:
//   - Stream::advance throws StreamOverrunException past the buffer end
//   - LStream is default-constructed; advance(len) accumulates; getLength()
//   - Serializer<bool>: one uint8_t wire byte per element, 0x00/0x01
//   - the uint32 element-count prefix belongs to streamVectorSize at the call
//     site; the functions under test never write it (no duplication here:
//     this driver writes the prefix exactly like the generated call site).

#include <cstdint>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <vector>

#include <ros/serialization.h>

namespace ros1_bridge
{
#include "stream_primitive_vector.inc"
}  // namespace ros1_bridge

namespace
{

int failures = 0;

void check(bool condition, const char* what)
{
  if (!condition) {
    std::cerr << "FAIL: " << what << std::endl;
    ++failures;
  }
}

// Mirrors the generated call site: streamVectorSize then streamPrimitiveVector.
template<typename VEC_T>
uint32_t serializeVector(const VEC_T& vec, uint8_t* out, uint32_t capacity)
{
  ros::serialization::OStream stream(out, capacity);
  uint32_t data_len = static_cast<uint32_t>(vec.size());
  stream.next(data_len);  // the helper-owned length prefix
  ros1_bridge::streamPrimitiveVector(stream, vec);
  return 4 + data_len * sizeof(typename VEC_T::value_type);
}

template<typename VEC_T>
VEC_T deserializeVector(const uint8_t* in, uint32_t capacity)
{
  ros::serialization::IStream stream(const_cast<uint8_t*>(in), capacity);
  uint32_t data_len = 0;
  stream.next(data_len);  // the helper-owned length prefix
  VEC_T vec(data_len, typename VEC_T::value_type());
  ros1_bridge::streamPrimitiveVector(stream, vec);
  return vec;
}

template<typename VEC_T>
uint32_t payloadLength(const VEC_T& vec)
{
  ros::serialization::LStream length_stream;
  ros1_bridge::streamPrimitiveVector(length_stream, vec);
  return length_stream.getLength();
}

}  // namespace

int main()
{
  uint8_t buffer[64];

  // 1. Empty vector<bool>: 4-byte prefix only, zero payload, roundtrip empty.
  {
    std::vector<bool> empty;
    check(payloadLength(empty) == 0, "empty bool vector payload length must be 0");
    uint32_t written = serializeVector(empty, buffer, sizeof(buffer));
    check(written == 4, "empty bool vector must serialize to the 4-byte prefix only");
    uint32_t len_le = 0;
    memcpy(&len_le, buffer, 4);
    check(len_le == 0, "empty bool length prefix must be 0");
    std::vector<bool> back = deserializeVector<std::vector<bool> >(buffer, written);
    check(back.empty(), "empty bool roundtrip must stay empty");
  }

  // 2. Empty vector<uint8_t>: generic fast path must not touch front().
  {
    std::vector<uint8_t> empty;
    check(payloadLength(empty) == 0, "empty uint8 vector payload length must be 0");
    uint32_t written = serializeVector(empty, buffer, sizeof(buffer));
    check(written == 4, "empty uint8 vector must serialize to the 4-byte prefix only");
    std::vector<uint8_t> back = deserializeVector<std::vector<uint8_t> >(buffer, written);
    check(back.empty(), "empty uint8 roundtrip must stay empty");
  }

  // 3. Mixed bool: exact wire bytes, matching Serializer<bool> element semantics.
  {
    std::vector<bool> mixed;
    mixed.push_back(true);
    mixed.push_back(false);
    mixed.push_back(true);
    mixed.push_back(true);
    check(payloadLength(mixed) == 4, "4 bools must occupy 4 payload bytes");
    uint32_t written = serializeVector(mixed, buffer, sizeof(buffer));
    check(written == 8, "4-element bool vector must serialize to 4+4 bytes");
    uint32_t len_le = 0;
    memcpy(&len_le, buffer, 4);
    check(len_le == 4, "bool length prefix must equal element count");
    // Cross-check every element byte against the real ROS Serializer<bool>.
    for (size_t i = 0; i < mixed.size(); ++i) {
      uint8_t ref[1] = {0};
      ros::serialization::OStream ref_stream(ref, sizeof(ref));
      ros::serialization::serialize(ref_stream, static_cast<bool>(mixed[i]));
      check(buffer[4 + i] == ref[0],
            "bool element wire byte must match ros::serialization::Serializer<bool>");
    }
    check(buffer[4] == 1 && buffer[5] == 0 && buffer[6] == 1 && buffer[7] == 1,
          "bool wire bytes must be 0x00/0x01 in element order");
    std::vector<bool> back = deserializeVector<std::vector<bool> >(buffer, written);
    check(back.size() == 4, "mixed bool roundtrip size");
    check(back[0] && !back[1] && back[2] && back[3],
          "mixed false/true roundtrip must preserve element values");
  }

  // 4. All-false non-empty roundtrip (the FormationAssign failure shape).
  {
    std::vector<bool> zeros(5, false);
    uint32_t written = serializeVector(zeros, buffer, sizeof(buffer));
    check(written == 9, "5-element bool vector must serialize to 4+5 bytes");
    std::vector<bool> back = deserializeVector<std::vector<bool> >(buffer, written);
    check(back.size() == 5, "all-false roundtrip size");
    bool any_true = false;
    for (size_t i = 0; i < back.size(); ++i) { any_true = any_true || back[i]; }
    check(!any_true, "all-false roundtrip must preserve false values");
  }

  // 5. Truncated input: a prefix claiming 4 elements with only 2 payload
  // bytes must throw StreamOverrunException, never read out of bounds.
  {
    uint8_t truncated[6] = {4, 0, 0, 0, 1, 0};
    bool threw = false;
    try {
      (void)deserializeVector<std::vector<bool> >(truncated, sizeof(truncated));
    } catch (const ros::serialization::StreamOverrunException&) {
      threw = true;
    }
    check(threw, "truncated bool payload must throw StreamOverrunException");
  }

  // 6. Generic memcpy fast path preserved for non-empty uint8.
  {
    std::vector<uint8_t> bytes;
    bytes.push_back(0xDE);
    bytes.push_back(0xAD);
    bytes.push_back(0xBE);
    bytes.push_back(0xEF);
    uint32_t written = serializeVector(bytes, buffer, sizeof(buffer));
    check(written == 8, "4-element uint8 vector must serialize to 4+4 bytes");
    check(buffer[4] == 0xDE && buffer[5] == 0xAD && buffer[6] == 0xBE && buffer[7] == 0xEF,
          "uint8 fast path must keep raw memcpy wire bytes");
  }

  // Noncanonical nonzero wire bytes use the same bool conversion as ROS1.
  {
    uint8_t wire[7] = {3, 0, 0, 0, 0, 2, 255};
    auto values = deserializeVector<std::vector<bool>>(wire, sizeof(wire));
    for (size_t i = 0; i < values.size(); ++i) {
      bool expected = false;
      ros::serialization::IStream reference(wire + 4 + i, 1);
      ros::serialization::deserialize(reference, expected);
      check(values[i] == expected, "nonzero wire bool must match ROS1 conversion");
    }
  }

  if (failures != 0) {
    std::cerr << failures << " check(s) failed" << std::endl;
    return 1;
  }
  std::cout << "vector<bool> ROS1 serialization checks passed" << std::endl;
  return 0;
}
