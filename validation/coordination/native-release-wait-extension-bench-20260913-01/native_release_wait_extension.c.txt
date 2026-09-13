/* Direct CPython extension candidate for wksim#84, bypassing libffi/ctypes.
 * Not wired into any production pacer or runner.
 *
 * wait_until(deadline_ns) is METH_O and reuses wk_release_wait_until from
 * native_release_wait.c (compiled together, see compile_argv in the loader).
 * bool, non-exact-int, negative and int64-overflowing deadlines are rejected
 * in C before the native call; any non-zero native status becomes an
 * exception; success returns the observed CLOCK_MONOTONIC ns, never early.
 * The bounded (<=1ms at entry) wait runs with the GIL held: no
 * Py_BEGIN_ALLOW_THREADS, matching the candidate's low-latency intent.
 */
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stdint.h>

int wk_release_wait_until(int64_t deadline_ns, int64_t *observed_ns);

static const char *const STATUS_NAMES[] = {
    "ok", "invalid_argument", "clock_failure", "clock_regressed",
    "deadline_out_of_range",
};

static PyObject *py_wait_until(PyObject *Py_UNUSED(module), PyObject *deadline) {
    long long value;
    int64_t observed_ns;
    int status;

    if (PyBool_Check(deadline)) {
        PyErr_SetString(PyExc_TypeError, "deadline_ns must be an int, not bool");
        return NULL;
    }
    if (!PyLong_CheckExact(deadline)) {
        PyErr_SetString(PyExc_TypeError, "deadline_ns must be an exact int");
        return NULL;
    }
    value = PyLong_AsLongLong(deadline);
    if (value == -1 && PyErr_Occurred())
        return NULL;                    /* OverflowError for int64 overflow */
    if (value < 0) {
        PyErr_SetString(PyExc_ValueError, "deadline_ns must be >= 0");
        return NULL;
    }

    status = wk_release_wait_until((int64_t)value, &observed_ns);
    if (status != 0) {
        const char *name = (status >= 1 && status <= 4)
            ? STATUS_NAMES[status] : "unknown_status";
        if (status == 1)
            PyErr_Format(PyExc_ValueError, "native wait failed: %s", name);
        else
            PyErr_Format(PyExc_RuntimeError, "native wait failed: %s (%d)",
                         name, status);
        return NULL;
    }
    return PyLong_FromLongLong((long long)observed_ns);
}

static PyMethodDef release_wait_methods[] = {
    {"wait_until", py_wait_until, METH_O,
     "wait_until(deadline_ns) -> observed CLOCK_MONOTONIC ns >= deadline"},
    {NULL, NULL, 0, NULL},
};

static struct PyModuleDef release_wait_module = {
    PyModuleDef_HEAD_INIT,
    .m_name = "_wksim_release_wait_native",
    .m_doc = NULL,
    .m_size = -1,
    .m_methods = release_wait_methods,
    .m_slots = NULL,
    .m_traverse = NULL,
    .m_clear = NULL,
    .m_free = NULL,
};

PyMODINIT_FUNC PyInit__wksim_release_wait_native(void) {
    PyObject *module = PyModule_Create(&release_wait_module);
    if (module == NULL)
        return NULL;
    if (PyModule_AddStringConstant(module, "CLOCK_DOMAIN",
                                   "CLOCK_MONOTONIC") < 0 ||
        PyModule_AddIntConstant(module, "SPIN_LIMIT_NS", 1000000) < 0 ||
        PyModule_AddStringConstant(module, "PYTHON_VERSION", PY_VERSION) < 0) {
        Py_DECREF(module);
        return NULL;
    }
    return module;
}
