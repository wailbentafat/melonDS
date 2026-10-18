/*
    Webcam hand-gesture input, embedded via CPython.

    Runs MediaPipe hand tracking (tools/gesture/gesture_engine.py) on its
    own dedicated thread, independent of EmuThread's NDS emulation rate —
    camera capture + inference take real time (tens of milliseconds) and
    must never block the emulator from hitting its own frame rate.
    EmuThread's per-frame Poll() just reads the latest cached result.

    No window capture, no synthetic OS input events — melonDS is the
    window, and this just feeds its own input/touch state each frame.
*/

#ifndef GESTURECONTROLLER_H
#define GESTURECONTROLLER_H

#include <QImage>
#include <QMutex>
#include <QString>

#include <atomic>
#include <thread>

class EmuInstance;

struct GestureSnapshot
{
    bool left = false, right = false, accel = false, brake = false, item = false;
    bool touching = false;
    int touchX = 0, touchY = 0;
    bool bothHandsVisible = false;
    QImage frame;
};

class GestureController
{
public:
    GestureController();
    ~GestureController();

    // Cheap: just records where gesture_engine.py lives. Call this from
    // the main thread at startup.
    void Prepare(const QString& scriptDir);

    // Cheap: starts the worker thread on first call (lazily, so camera
    // open / MediaPipe model load never blocks the main thread), then
    // just copies the latest cached snapshot into emuInstance. Call this
    // once per emulated frame from EmuThread.
    void Poll(EmuInstance* emuInstance);

    void Shutdown();

    bool IsActive() const { return active.load(); }
    QImage WebcamFrame(); // thread-safe copy, for a UI overlay

private:
    void WorkerLoop(); // runs entirely on captureThread

    std::atomic<bool> active{false};
    std::atomic<bool> started{false};
    std::atomic<bool> stopRequested{false};
    std::thread captureThread;

    // Only ever touched from Poll(), always called from EmuThread — no
    // synchronization needed.
    bool wasActiveLastPoll = false;

    QString scriptDir;

    QMutex snapshotMutex;
    GestureSnapshot snapshot;

    // Opaque PyObject* — kept void* so Python.h doesn't need to be
    // visible (and fighting with Qt headers) outside GestureController.cpp.
    // Only ever touched from captureThread.
    void* module = nullptr;
    void* initFunc = nullptr;
    void* pollFunc = nullptr;
    void* shutdownFunc = nullptr;
};

#endif // GESTURECONTROLLER_H
