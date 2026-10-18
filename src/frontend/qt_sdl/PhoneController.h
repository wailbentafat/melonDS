/*
    Phone controller input, embedded via CPython — one per EmuInstance
    that picks "Phone" at the DS64 Setup dialog.

    Each instance gets its own listener on its own port (see
    PhoneController::Prepare), driven by tools/phone/phone_bridge.py
    (a synchronous websockets server run on its own thread). This is
    what makes multi-phone local multiplayer work: every instance has a
    focus-independent, process-direct input channel, instead of one
    external process guessing which OS-focused window should receive
    synthetic keystrokes.

    Structurally a near-twin of GestureController — same worker-thread +
    mutex-protected-snapshot pattern, same Python-embedding GIL rules.
*/

#ifndef PHONECONTROLLER_H
#define PHONECONTROLLER_H

#include <QMutex>
#include <QString>

#include <atomic>
#include <thread>

class EmuInstance;

struct PhoneSnapshot
{
    bool connected = false;
    bool left = false, right = false, accel = false, brake = false;
    bool drift = false, item = false;
};

class PhoneController
{
public:
    PhoneController();
    ~PhoneController();

    // Cheap: just records where phone_bridge.py lives and which port to
    // listen on. Call this from the main thread at startup.
    void Prepare(const QString& scriptDir, int port);

    // Cheap: starts the worker thread on first call (lazily), then just
    // copies the latest cached snapshot into emuInstance. Call this once
    // per emulated frame from EmuThread.
    void Poll(EmuInstance* emuInstance);

    void Shutdown();

    bool IsActive() const { return active.load(); }
    bool IsConnected() const { return connected.load(); }

private:
    void WorkerLoop(); // runs entirely on listenThread

    std::atomic<bool> active{false};
    std::atomic<bool> connected{false};
    std::atomic<bool> started{false};
    std::atomic<bool> stopRequested{false};
    std::thread listenThread;

    QString scriptDir;
    int port = 0;

    QMutex snapshotMutex;
    PhoneSnapshot snapshot;

    // Only ever touched from listenThread.
    void* module = nullptr;
    void* initFunc = nullptr;
    void* pollFunc = nullptr;
    void* shutdownFunc = nullptr;
    // The per-instance session object init() returns — all EmuInstances
    // share one embedded interpreter, so the phone_bridge module object
    // itself is shared (sys.modules caches by name); this is what keeps
    // each instance's connection/state actually separate. Passed back
    // into poll()/shutdown() every call.
    void* sessionObj = nullptr;

    bool wasActiveLastPoll = false;
};

#endif // PHONECONTROLLER_H
