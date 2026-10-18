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

    // Cheap: just records where gesture_engine.py lives. Call this from
    // the main thread at startup.
    void Prepare(const QString& scriptDir);

    // Poll() does the real (slow: camera open + MediaPipe model load,
    // possibly blocked on a camera-permission prompt) initialization on
    // its first call, lazily, on whatever thread calls it (EmuThread) —
    // never from the main/UI thread, or it can stall the window from
    // ever appearing if macOS is waiting on a permission dialog nobody
    // can click from a background-launched process.
    void Poll(EmuInstance* emuInstance);
    void Shutdown();

    bool IsActive() const { return active; }
    const QImage& WebcamFrame() const { return webcamFrame; }

private:
    bool InitInternal();

    bool active = false;
    bool initAttempted = false;
    QString scriptDir;

    // Opaque PyObject* — kept void* so Python.h doesn't need to be
    // visible (and fighting with Qt headers) outside GestureController.cpp.
    void* module = nullptr;
    void* initFunc = nullptr;
    void* pollFunc = nullptr;
    void* shutdownFunc = nullptr;

    QImage webcamFrame;
};

#endif // GESTURECONTROLLER_H
