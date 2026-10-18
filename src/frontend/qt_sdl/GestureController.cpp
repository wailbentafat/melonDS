// Python.h must be the first include in this file: it pins certain POSIX
// feature-test macros (_POSIX_C_SOURCE etc.) that must be set before any
// system or Qt header transitively pulls in <unistd.h>/<stdio.h>. Including
// Qt headers first causes macro-redefinition errors against Python.h.
#include <Python.h>

#include "GestureController.h"
#include "EmuInstance.h"

#include <QDebug>

namespace
{

QByteArray PyStrToQByteArray(PyObject* dict, const char* key)
{
    PyObject* v = PyDict_GetItemString(dict, key);
    if (!v || !PyUnicode_Check(v))
        return {};
    return QByteArray(PyUnicode_AsUTF8(v));
}

long PyLongFromDict(PyObject* dict, const char* key)
{
    PyObject* v = PyDict_GetItemString(dict, key);
    return v ? PyLong_AsLong(v) : 0;
}

bool PyBoolFromDict(PyObject* dict, const char* key)
{
    PyObject* v = PyDict_GetItemString(dict, key);
    return v && PyObject_IsTrue(v);
}

} // namespace

GestureController::GestureController() = default;

GestureController::~GestureController()
{
    Shutdown();
}

bool GestureController::Init(const QString& scriptDir)
{
    if (!Py_IsInitialized())
        Py_Initialize();

    PyObject* sysPath = PySys_GetObject("path");
    if (sysPath)
    {
        PyObject* dir = PyUnicode_FromString(scriptDir.toUtf8().constData());
        PyList_Append(sysPath, dir);
        Py_DECREF(dir);
    }

    PyObject* name = PyUnicode_FromString("gesture_engine");
    PyObject* mod = PyImport_Import(name);
    Py_DECREF(name);

    if (!mod)
    {
        PyErr_Print();
        qWarning() << "GestureController: failed to import gesture_engine";
        return false;
    }
    module = mod;

    PyObject* initFn = PyObject_GetAttrString(mod, "init");
    PyObject* pollFn = PyObject_GetAttrString(mod, "poll");
    PyObject* shutdownFn = PyObject_GetAttrString(mod, "shutdown");

    if (!initFn || !pollFn || !shutdownFn)
    {
        PyErr_Print();
        qWarning() << "GestureController: gesture_engine missing init/poll/shutdown";
        return false;
    }
    initFunc = initFn;
    pollFunc = pollFn;
    shutdownFunc = shutdownFn;

    PyObject* result = PyObject_CallObject((PyObject*)initFunc, nullptr);
    bool ok = result && PyObject_IsTrue(result);
    if (!result)
        PyErr_Print();
    Py_XDECREF(result);

    active = ok;
    if (!ok)
        qWarning() << "GestureController: camera/hand-tracking init failed "
                       "(check camera permission and requirements.txt deps)";

    return ok;
}

void GestureController::Poll(EmuInstance* emuInstance)
{
    if (!active || !pollFunc || !emuInstance)
        return;

    PyObject* result = PyObject_CallObject((PyObject*)pollFunc, nullptr);
    if (!result)
    {
        PyErr_Print();
        return;
    }

    QByteArray direction = PyStrToQByteArray(result, "direction");
    QByteArray throttle  = PyStrToQByteArray(result, "throttle");
    bool touching = PyBoolFromDict(result, "touching");
    int touchX = (int)PyLongFromDict(result, "touch_x");
    int touchY = (int)PyLongFromDict(result, "touch_y");

    bool left  = direction == "LEFT";
    bool right = direction == "RIGHT";
    bool accel = throttle == "ACCEL";
    bool brake = throttle == "BRAKE";

    emuInstance->setGestureKeys(left, right, accel, brake);

    if (touching)
        emuInstance->touchScreen(touchX, touchY);
    else
        emuInstance->releaseScreen();

    PyObject* frameObj = PyDict_GetItemString(result, "frame");
    int frameW = (int)PyLongFromDict(result, "frame_w");
    int frameH = (int)PyLongFromDict(result, "frame_h");

    if (frameObj && PyBytes_Check(frameObj) && frameW > 0 && frameH > 0)
    {
        Py_ssize_t len = PyBytes_Size(frameObj);
        if (len >= (Py_ssize_t)frameW * frameH * 3)
        {
            const uchar* data = (const uchar*)PyBytes_AsString(frameObj);
            QImage img(data, frameW, frameH, frameW * 3, QImage::Format_BGR888);
            webcamFrame = img.copy(); // detach from Python-owned buffer
        }
    }

    Py_DECREF(result);
}

void GestureController::Shutdown()
{
    if (shutdownFunc)
    {
        PyObject* result = PyObject_CallObject((PyObject*)shutdownFunc, nullptr);
        if (!result)
            PyErr_Print();
        Py_XDECREF(result);
    }

    Py_XDECREF((PyObject*)initFunc);
    Py_XDECREF((PyObject*)pollFunc);
    Py_XDECREF((PyObject*)shutdownFunc);
    Py_XDECREF((PyObject*)module);

    initFunc = pollFunc = shutdownFunc = module = nullptr;
    active = false;
}
