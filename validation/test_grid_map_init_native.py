"""Compile GridMap's actual buffer-size guard with UBSan, without ROS.

Only the surrounding parameter storage and ROS logging are stubbed; the C++
guard is taken verbatim from grid_map.cpp, not reimplemented in Python.
"""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'Modules/ego_planner_swarm/plan_env/src/grid_map.cpp'


class GridMapNativeInitializationTests(unittest.TestCase):
    def test_invalid_initialization_cannot_return_to_the_planner(self):
        source = SOURCE.read_text(encoding='utf-8')
        body = source.split('void GridMap::initMap(', 1)[1].split(
            'void GridMap::gridparam_Callback', 1)[0]
        self.assertNotIn('return;', body)
        self.assertIn('throw std::invalid_argument', body)

    @unittest.skipUnless(sys.platform == 'linux' and shutil.which('g++'),
                         'requires Linux g++ with UBSan')
    def test_actual_cpp_buffer_guard_rejects_before_signed_overflow(self):
        source = SOURCE.read_text(encoding='utf-8')
        guard = source.split('// initialize data buffers', 1)[1].split(
            'md_.occupancy_buffer_ =', 1)[0]
        helpers = source.split('namespace {', 1)[1].split('}  // namespace', 1)[0]
        program = r'''
#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <iostream>
#define ROS_ERROR_STREAM(message) do {} while (false)
template<typename T> struct Triple {
  T entries[3];
  T operator()(int axis) const { return entries[axis]; }
};
struct MappingParameters {
  double resolution_;
  Triple<double> map_size_;
  Triple<int> map_voxel_num_;
};
''' + helpers + r'''
struct Harness {
  struct Params {
    int counts[3];
    int map_voxel_num_(int axis) const { return counts[axis]; }
  } mp_;
  int allocated = -1;
  void initialize() {
''' + guard + r'''
    allocated = buffer_size;
  }
};
int main() {
  const int m = std::numeric_limits<int>::max();
  const int cases[][4] = {
    {m,m,m,-1}, {2097152,2097152,2097152,-1},
    {46341,46341,1,-1}, {m,2,1,-1},
    {1,1,1,1}, {200,120,60,1440000}, {m,1,1,m}
  };
  for (const auto& c : cases) {
    Harness h{{{c[0],c[1],c[2]}}};
    bool rejected = false;
    try { h.initialize(); }
    catch (const std::invalid_argument&) { rejected = true; }
    if (c[3] == -1) {
      if (!rejected || h.allocated != -1) return 1;
    } else if (rejected || h.allocated != c[3]) return 2;
  }
  MappingParameters params{0.1, {{20,12,6}}, {{200,120,60}}};
  if (checkedInflationSteps(0.8, params) != 8 ||
      checkedInflationSteps(-0.1, params) != -1 ||
      checkedInflationSteps(0.0, params) != 0 ||
      checkedInflationSteps(std::numeric_limits<double>::infinity(), params) != -1 ||
      checkedInflationSteps(std::numeric_limits<double>::quiet_NaN(), params) != -1) return 3;
  params = {1.0, {{100,100,100}}, {{100,100,100}}};
  if (checkedInflationSteps(32, params) != 32 ||
      checkedInflationSteps(33, params) != -1) return 4;
  params.resolution_ = 0;
  if (checkedInflationSteps(1, params) != -1) return 5;
  std::cout << "7 actual C++ guard cases passed\n";
}
'''
        with tempfile.TemporaryDirectory(prefix='wksim-grid-ubsan-') as temp:
            directory = Path(temp)
            cpp = directory / 'probe.cpp'
            binary = directory / 'probe'
            cpp.write_text(program, encoding='utf-8')
            built = subprocess.run(
                ['g++', '-std=c++17', '-O1', '-fsanitize=undefined',
                 '-fno-sanitize-recover=all', str(cpp), '-o', str(binary)],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(built.returncode, 0, built.stderr)
            result = subprocess.run([str(binary)], capture_output=True,
                                    text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(result.stderr, '')
            self.assertIn('7 actual C++ guard cases passed', result.stdout)


if __name__ == '__main__':
    unittest.main()
