/*
    Copyright 2016-2026 melonDS team

    This file is part of melonDS.

    melonDS is free software: you can redistribute it and/or modify it under
    the terms of the GNU General Public License as published by the Free
    Software Foundation, either version 3 of the License, or (at your option)
    any later version.

    melonDS is distributed in the hope that it will be useful, but WITHOUT ANY
    WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
    FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

    You should have received a copy of the GNU General Public License along
    with melonDS. If not, see http://www.gnu.org/licenses/.
*/

#ifndef WINDOW_H
#define WINDOW_H

#include "glad/glad.h"
#include "ScreenLayout.h"
#include "duckstation/gl/context.h"

#include <QWidget>
#include <QWindow>
#include <QMainWindow>
#include <QImage>
#include <QActionGroup>
#include <QTimer>
#include <QMutex>
#include <QScreen>
#include <QCloseEvent>
#include <QLabel>
#include <QGridLayout>

#include "Screen.h"
#include "Config.h"
#include "MPInterface.h"


class EmuInstance;
class EmuThread;
class QPushButton;

const int kMaxRecentROMs = 10;

class MainWindow : public QMainWindow
{
    Q_OBJECT

public:
    explicit MainWindow(int id, EmuInstance* inst, QWidget* parent = nullptr);
    ~MainWindow();

    EmuInstance* getEmuInstance() { return emuInstance; }
    Config::Table& getWindowConfig() { return windowCfg; }
    int getWindowID() { return windowID; }

    bool winHasMenu() { return hasMenu; }

    void saveEnabled(bool enabled);

    void toggleFullscreen();

    bool hasOpenGL() { return hasOGL; }
    GL::Context* getOGLContext();
    void initOpenGL();
    void deinitOpenGL();
    void setGLSwapInterval(int intv);
    void makeCurrentGL();
    void releaseGL();

    void drawScreen();

    // DS64 split-screen: embeds a new ScreenPanel bound to inst into
    // this window's multiplayerGrid, instead of inst getting its own
    // top-level window. See EmuInstance.cpp's constructor.
    void addMultiplayerPanel(EmuInstance* inst);

    bool preloadROMs(QStringList file, QStringList gbafile, bool boot);
    QStringList splitArchivePath(const QString& filename, bool useMemberSyntax);

    void onAppStateChanged(Qt::ApplicationState state);

    void onFocusIn();
    void onFocusOut();
    bool isFocused() { return focused; }

    void osdAddMessage(unsigned int color, const char* msg);

    // called when the MP interface is changed
    void updateMPInterface(melonDS::MPInterfaceType type);

    void loadRecentFilesMenu(bool loadcfg);
    //void updateVideoSettings(bool glchange);

protected:
    void keyPressEvent(QKeyEvent* event) override;
    void keyReleaseEvent(QKeyEvent* event) override;

    void dragEnterEvent(QDragEnterEvent* event) override;
    void dropEvent(QDropEvent* event) override;

    void focusInEvent(QFocusEvent* event) override;
    void focusOutEvent(QFocusEvent* event) override;

signals:
    void screenLayoutChange();

private slots:
    void onOpenFile();
    void onClickRecentFile();
    void onClearRecentFiles();
    void onBootFirmware();
    void onInsertCart();
    void onEjectCart();
    void onInsertGBACart();
    void onInsertGBAAddon();
    void onEjectGBACart();
    void onSaveState();
    void onLoadState();
    void onUndoStateLoad();
    void onImportSavefile();
    void onQuit();

    void onPause(bool checked);
    void onReset();
    void onStop();
    void onFrameStep();
    void onOpenPowerManagement();
    void onOpenDateTime();
    void onDateTimeDialogFinished(int res);
    void onEnableCheats(bool checked);
    void onSetupCheats();
    void onCheatsDialogFinished(int res);
    void onROMInfo();
    void onRAMInfo();
    void onOpenTitleManager();
    void onMPNewInstance();
    // Restarts the whole app with the same launch arguments (same ROM),
    // so the native DS64 Setup dialog (camera/phone, player count) asks
    // again from scratch — see EmuInstance.cpp's constructor. Tearing
    // down and rebuilding the multi-instance/grid state in place would
    // be far more fragile than just reusing the already-tested startup
    // path via a clean relaunch.
    void onDS64Setup();
    void onLANStartHost();
    void onLANStartClient();
    void onNPStartHost();
    void onNPStartClient();
    void onNPTest();

    void onOpenEmuSettings();
    void onEmuSettingsDialogFinished(int res);
    void onOpenInputConfig();
    void onInputConfigFinished(int res);
    void onOpenVideoSettings();
    void onOpenCameraSettings();
    void onCameraSettingsFinished(int res);
    void onOpenAudioSettings();
    void onUpdateAudioVolume(int vol, int dsisync);
    void onUpdateAudioSettings();
    void onAudioSettingsFinished(int res);
    void onOpenMPSettings();
    void onMPSettingsFinished(int res);
    void onOpenWifiSettings();
    void onWifiSettingsFinished(int res);
    void onOpenFirmwareSettings();
    void onFirmwareSettingsFinished(int res);
    void onOpenPathSettings();
    void onPathSettingsFinished(int res);
    void onOpenInterfaceSettings();
    void onInterfaceSettingsFinished(int res);
    void onUpdateInterfaceSettings();
    void onChangeScreenSize();
    void onChangeScreenRotation(QAction* act);
    void onChangeScreenGap(QAction* act);
    void onChangeScreenLayout(QAction* act);
    void onChangeScreenSwap(bool checked);
    void onChangeScreenSizing(QAction* act);
    void onChangeScreenAspect(QAction* act);
    void onChangeIntegerScaling(bool checked);
    void onOpenNewWindow();
    void onChangeScreenFiltering(bool checked);
    void onChangeShowOSD(bool checked);
    void onChangeLimitFramerate(bool checked);
    void onChangeAudioSync(bool checked);

    void onTitleUpdate(QString title);

    void onEmuStart();
    void onEmuStop();
    void onEmuPause(bool pause);
    void onEmuReset();

    void onUpdateVideoSettings(bool glchange);

    void onFullscreenToggled();
    void onScreenEmphasisToggled();

private:
    virtual void closeEvent(QCloseEvent* event) override;

    QStringList currentROM;
    QStringList currentGBAROM;
    QList<QString> recentFileList;
    QMenu *recentMenu;
    void updateRecentFilesMenu();

    bool verifySetup();
    QString pickFileFromArchive(QString archiveFileName);
    QStringList pickROM(bool gba);
    void updateCartInserted(bool gba);

    void createScreenPanel();

    bool lanWarning(bool host);

    // Webcam + wheel/HUD picture-in-picture, drawn entirely on the
    // Python side (see tools/gesture/gesture_engine.py) — this just
    // displays whatever image GestureController last produced.
    QLabel* gestureOverlay = nullptr;
    QTimer* gestureOverlayTimer = nullptr;
    void updateGestureOverlay();

    // Phone-controller QR code for this instance, shown when it's
    // phone-controlled (predictable path by instance id — see
    // tools/make_controller_qr.py) — a static image, no live updates
    // needed like the gesture overlay.
    QLabel* qrOverlay = nullptr;

    // Always-visible on-screen button back to the DS64 Setup picker —
    // the equivalent menu item (System > Multiplayer > DS64 Setup...)
    // isn't reachable if the window is in native macOS fullscreen, which
    // hides the whole menu bar. This sits directly on the game screen
    // instead, so it's reachable no matter the window state.
    QPushButton* reloadButton = nullptr;

    // DS64 split-screen: when a multi-phone session is active, instance
    // 0 is the only one with a real top-level window — every other
    // instance gets a ScreenPanel embedded into this grid instead of
    // its own window (see addMultiplayerPanel, public below).
    QGridLayout* multiplayerGrid = nullptr;

    bool showOSD;

    bool hasOGL;

    bool pauseOnLostFocus;
    bool pausedManually;

    int windowID;
    bool enabledSaved;

    bool focused;

    EmuInstance* emuInstance;
    EmuThread* emuThread;

    Config::Table& globalCfg;
    Config::Table& localCfg;
    Config::Table windowCfg;

public:
    ScreenPanel* panel;

    bool hasMenu;

    QAction* actOpenROM;
    QAction* actBootFirmware;
    QAction* actCurrentCart;
    QAction* actInsertCart;
    QAction* actEjectCart;
    QAction* actCurrentGBACart;
    QAction* actInsertGBACart;
    QList<QAction*> actInsertGBAAddon;
    QAction* actEjectGBACart;
    QAction* actImportSavefile;
    QAction* actSaveState[9];
    QAction* actLoadState[9];
    QAction* actUndoStateLoad;
    QAction* actOpenConfig;
    QAction* actQuit;

    QAction* actPause;
    QAction* actReset;
    QAction* actStop;
    QAction* actFrameStep;
    QAction* actPowerManagement;
    QAction* actDateTime;
    QAction* actEnableCheats;
    QAction* actSetupCheats;
    QAction* actROMInfo;
    QAction* actRAMInfo;
    QAction* actTitleManager;
    QAction* actMPNewInstance;
    QAction* actDS64Setup;
    QAction* actLANStartHost;
    QAction* actLANStartClient;
    QAction* actNPStartHost;
    QAction* actNPStartClient;
    QAction* actNPTest;

    QAction* actEmuSettings;
#ifdef __APPLE__
    QAction* actPreferences;
#endif
    QAction* actInputConfig;
    QAction* actVideoSettings;
    QAction* actCameraSettings;
    QAction* actAudioSettings;
    QAction* actMPSettings;
    QAction* actWifiSettings;
    QAction* actFirmwareSettings;
    QAction* actPathSettings;
    QAction* actInterfaceSettings;
    QAction* actScreenSize[4];
    QActionGroup* grpScreenRotation;
    QAction* actScreenRotation[screenRot_MAX];
    QActionGroup* grpScreenGap;
    QAction* actScreenGap[6];
    QActionGroup* grpScreenLayout;
    QAction* actScreenLayout[screenLayout_MAX];
    QAction* actScreenSwap;
    QActionGroup* grpScreenSizing;
    QAction* actScreenSizing[screenSizing_MAX];
    QAction* actIntegerScaling;
    QActionGroup* grpScreenAspectTop;
    QAction** actScreenAspectTop;
    QActionGroup* grpScreenAspectBot;
    QAction** actScreenAspectBot;
    QAction* actNewWindow;
    QAction* actScreenFiltering;
    QAction* actShowOSD;
    QAction* actLimitFramerate;
    QAction* actAudioSync;

    QAction* actAbout;
};

#endif // WINDOW_H
