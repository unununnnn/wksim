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
HEADER = ROOT / 'Modules/ego_planner_swarm/plan_env/include/plan_env/grid_map.h'


def function_span(source, signature):
    """Return the source of one GridMap member function definition."""
    start = source.index(signature)
    end = source.index('\nvoid GridMap::', start + len(signature))
    return source[start:end]


def inline_body(header, signature):
    """Return the verbatim body of an inline header function."""
    start = header.index(signature)
    open_brace = header.index('{', start)
    depth = 0
    for pos in range(open_brace, len(header)):
        char = header[pos]
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                return header[open_brace + 1:pos]
    raise AssertionError('unbalanced braces in ' + signature)


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
  Triple<double> map_origin_{};
  double resolution_inv_ = 0.0;
  double virtual_ceil_height_ = -1.0;
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
  MappingParameters ceiling{0.1, {{20,12,6}}, {{200,120,60}}, {{0,0,0}}, 10.0, 5.5};
  int ceil_id = -1;
  if (!checkedVirtualCeilingId(ceiling, ceil_id) || ceil_id != 54) return 6;
  ceiling.virtual_ceil_height_ = -0.1;
  if (checkedVirtualCeilingId(ceiling, ceil_id) || ceil_id != -1) return 7;
  ceiling.virtual_ceil_height_ = -0.5;
  if (!checkedVirtualCeilingId(ceiling, ceil_id) || ceil_id != -1) return 8;
  ceiling.virtual_ceil_height_ = std::numeric_limits<double>::quiet_NaN();
  if (checkedVirtualCeilingId(ceiling, ceil_id) || ceil_id != -1) return 9;
  ceiling.virtual_ceil_height_ = std::numeric_limits<double>::infinity();
  if (checkedVirtualCeilingId(ceiling, ceil_id) || ceil_id != -1) return 10;
  ceiling.virtual_ceil_height_ = 1e300;
  if (checkedVirtualCeilingId(ceiling, ceil_id) || ceil_id != -1) return 11;
  std::cout << "actual C++ guard and ceiling cases passed\n";
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
            self.assertIn('actual C++ guard and ceiling cases passed', result.stdout)

    @unittest.skipUnless(sys.platform == 'linux' and shutil.which('g++'),
                         'requires Linux g++ with UBSan')
    def test_actual_cpp_inflation_geometry_and_index_guards(self):
        source = SOURCE.read_text(encoding='utf-8')
        header = HEADER.read_text(encoding='utf-8')
        helpers = source.split('namespace {', 1)[1].split('}  // namespace', 1)[0]
        to_address = inline_body(header,
                                 'inline int GridMap::toAddress(const Eigen::Vector3i& id)')
        is_in_map = inline_body(header,
                                'inline bool GridMap::isInMap(const Eigen::Vector3i& idx)')
        position_in_map = inline_body(header,
                                     'inline bool GridMap::isInMap(const Eigen::Vector3d& pos)')
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
  Triple<double> map_origin_{};
  double resolution_inv_ = 0.0;
  double virtual_ceil_height_ = -1.0;
};
template<typename T> struct Vec3 {
  T entries[3];
  T operator()(int axis) const { return entries[axis]; }
};
namespace Eigen { using Vector3i = Vec3<int>; using Vector3d = Vec3<double>; }
''' + helpers + r'''
struct Geometry {
  struct Params {
    int counts[3];
    int map_voxel_num_(int axis) const { return counts[axis]; }
    double map_min_boundary_(int) const { return 0.0; }
    double map_max_boundary_(int axis) const { return 0.1 * counts[axis]; }
  } mp_;
  int toAddress(const Eigen::Vector3i& id) {''' + to_address + r'''
  }
  bool isInMap(const Eigen::Vector3i& idx) {''' + is_in_map + r'''
  }
  bool isInMap(const Eigen::Vector3d& pos) {''' + position_in_map + r'''
  }
};
int main() {
  Geometry geo{{{200, 120, 60}}};
  // The base point is outside; its +1 voxel candidate must still be eligible.
  if (geo.isInMap(Eigen::Vector3d{{-0.05, 1.0, 1.0}}) ||
      !geo.isInMap(Eigen::Vector3d{{0.05, 1.0, 1.0}}) ||
      geo.isInMap(Eigen::Vector3d{{std::numeric_limits<double>::max(), 1.0, 1.0}})) return 20;
  const int buffer_size = 200 * 120 * 60;
  const Eigen::Vector3i overflow{{5, 5, 60}};   // one voxel past the top z layer
  const Eigen::Vector3i alias{{5, 6, 0}};       // valid voxel its flat address aliases
  const int flat = geo.toAddress(overflow);
  if (flat != geo.toAddress(alias)) return 1;    // the aliasing is real
  if (flat < 0 || flat >= buffer_size) return 2; // a flat range check would ACCEPT it
  if (geo.isInMap(overflow)) return 3;           // per-axis check REJECTS it
  if (!geo.isInMap(alias)) return 4;
  if (!geo.isInMap(Eigen::Vector3i{{0, 0, 0}})) return 5;
  if (!geo.isInMap(Eigen::Vector3i{{199, 119, 59}})) return 6;
  if (geo.isInMap(Eigen::Vector3i{{-1, 0, 0}})) return 7;
  if (geo.isInMap(Eigen::Vector3i{{0, 0, 60}})) return 8;
  // actual profile geometry: 0.8 m at 0.1 m resolution -> 8 steps/axis -> 17^3 cube
  const MappingParameters profile{0.1, {{20, 12, 6}}, {{200, 120, 60}}};
  const int steps = checkedInflationSteps(0.8, profile);
  if (steps != 8) return 9;
  const int side = 2 * steps + 1;
  if (side * side * side != 4913) return 10;
  // the shared cap: 32 steps/axis -> 65^3 candidate cube
  const MappingParameters coarse{1.0, {{100, 100, 100}}, {{100, 100, 100}}};
  const int cap = checkedInflationSteps(32, coarse);
  if (cap != 32) return 11;
  const int cap_side = 2 * cap + 1;
  if (cap_side * cap_side * cap_side != 274625) return 12;
  if (checkedInflationSteps(33, coarse) != -1) return 13;
  MappingParameters ceiling{0.1, {{20,12,6}}, {{200,120,60}}, {{0,0,0}}, 10.0, 5.5};
  int ceil_id = -1;
  if (!checkedVirtualCeilingId(ceiling, ceil_id) || ceil_id != 54) return 14;
  ceiling.virtual_ceil_height_ = -0.1;
  if (checkedVirtualCeilingId(ceiling, ceil_id) || ceil_id != -1) return 15;
  ceiling.virtual_ceil_height_ = std::numeric_limits<double>::quiet_NaN();
  if (checkedVirtualCeilingId(ceiling, ceil_id) || ceil_id != -1) return 16;
  std::cout << "actual C++ inflation geometry/index cases passed\n";
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
            self.assertIn('actual C++ inflation geometry/index cases passed',
                          result.stdout)


class GridMapInflationConsumerContractTests(unittest.TestCase):
    """Static contract for the unified three-axis inflation slice (no ROS)."""

    def test_virtual_ceiling_consumers_use_checked_in_map_index(self):
        source = SOURCE.read_text(encoding='utf-8')
        self.assertNotIn(
            'floor((mp_.virtual_ceil_height_ - mp_.map_origin_(2)) * mp_.resolution_inv_) - 1',
            source)
        self.assertIn('bool checkedVirtualCeilingId(const MappingParameters& params, int& ceil_id)',
                      source)
        for signature in (
                'void GridMap::clearAndInflateLocalMap(',
                'void GridMap::cloudCallback('):
            body = function_span(source, signature)
            self.assertIn('checkedVirtualCeilingId(mp_, ceil_id)', body)
            self.assertIn('ceil_id >= 0 && ceil_id < mp_.map_voxel_num_(2)', body)
        publish_body = function_span(source, 'void GridMap::publishMapInflate(')
        self.assertIn('checkedVirtualCeilingId(mp_, ceil_id)', publish_body)
        self.assertIn('has_valid_ceil && z == ceil_id', publish_body)
        init_body = source.split('void GridMap::initMap(', 1)[1].split(
            'void GridMap::gridparam_Callback', 1)[0]
        self.assertLess(
            init_body.index('!std::isfinite(mp_.ground_height_)'),
            init_body.index('mp_.virtual_ceil_height_ - mp_.ground_height_'))

    def test_no_divergent_z_inflation_semantics_remain(self):
        source = SOURCE.read_text(encoding='utf-8')
        self.assertNotIn('inf_step_z', source)
        self.assertNotIn('ceil(mp_.obstacles_inflation_', source)
        # initMap, clearAndInflateLocalMap and cloudCallback all share the helper
        self.assertEqual(
            source.count('checkedInflationSteps(mp_.obstacles_inflation_, mp_)'), 3)

    def test_clear_path_checks_each_axis_before_flat_address(self):
        body = function_span(SOURCE.read_text(encoding='utf-8'),
                             'void GridMap::clearAndInflateLocalMap(')
        self.assertIn('checkedInflationSteps(mp_.obstacles_inflation_, mp_)', body)
        # the flat-address range check that could alias an out-of-range axis is gone
        self.assertNotIn('idx_inf >= mp_.map_voxel_num_', body)
        self.assertLess(body.index('if (!isInMap(inf_pt))'),
                        body.index('toAddress(inf_pt)'))

    def test_cloud_rejects_non_finite_and_out_of_map_points_before_indexing(self):
        body = function_span(SOURCE.read_text(encoding='utf-8'),
                             'void GridMap::cloudCallback(')
        self.assertIn('checkedInflationSteps(mp_.obstacles_inflation_, mp_)', body)
        finite_skip = body.index('!std::isfinite(pt.x)')
        assignment = body.index('p3d(0) = pt.x')
        position_gate = body.index('if (!p3d_inf.allFinite() || !isInMap(p3d_inf))')
        self.assertNotIn('if (!isInMap(p3d))', body)
        self.assertLess(body.index('!isInMap(md_.camera_pos_)'), body.index('this->resetBuffer'))
        bound_growth = body.index('max_x = max(max_x')
        index_conversion = body.index('posToIndex(p3d_inf, inf_pt)')
        # non-finite points are dropped before any index arithmetic
        self.assertLess(finite_skip, assignment)
        # out-of-map points can neither reach posToIndex nor grow local_bound
        self.assertLess(position_gate, bound_growth)
        self.assertLess(position_gate, index_conversion)
        # z inflates by the same step count as x/y
        self.assertIn('for (int z = -inf_step; z <= inf_step; ++z)', body)

    def test_scan_callback_is_a_no_op_without_inflation(self):
        body = function_span(SOURCE.read_text(encoding='utf-8'),
                             'void GridMap::scanCallback(')
        self.assertIn('(void)laser_scan;', body)
        self.assertIn('return;', body)
        self.assertNotIn('ceil(', body)
        self.assertNotIn('checkedInflationSteps', body)
        self.assertNotIn('LaserProjection', body)
        self.assertNotIn('odom_uav', body)


if __name__ == '__main__':
    unittest.main()
