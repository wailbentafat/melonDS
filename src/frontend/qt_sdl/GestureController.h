/*
    Webcam hand-gesture input, embedded via CPython.

    Drives EmuInstance's steering/throttle keys and touch screen directly
    from a Python module (tools/gesture/gesture_engine.py) running
    MediaPipe hand tracking against the host webcam. No window capture,
    no synthetic OS input events — melonDS is the window, and this just
    feeds its own input state each frame.
*/

#ifndef GESTURECONTROLLER_H
#define GESTURECONTROLLER_H

#include <QImage>
#include <QString>

class EmuInstance;

class GestureController
{
public:
    GestureController();
    ~GestureController();

    // scriptDir is the folder containing gesture_engine.py.
    bool Init(const QString& scriptDir);
    void Poll(EmuInstance* emuInstance);
    void Shutdown();

    bool IsActive() const { return active; }
    const QImage& WebcamFrame() const { return webcamFrame; }

private:
    bool active = false;

    // Opaque PyObject* — kept void* so Python.h doesn't need to be
    // visible (and fighting with Qt headers) outside GestureController.cpp.
    void* module = nullptr;
    void* initFunc = nullptr;
    void* pollFunc = nullptr;
    void* shutdownFunc = nullptr;

    QImage webcamFrame;
};

#endif // GESTURECONTROLLER_H
