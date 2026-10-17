// SR2022 Cutscene Replay: dinput8.dll proxy. Hooks the game's cinematic tick (game thread)
// and lets F7/F8 pick a cinematic from the game's own registry and F9 play it.
// Offsets are for SaintsRow_DX12.exe (SizeOfImage 0x5f6a000); prologues are verified before hooking.
#include <windows.h>
#include <cstdarg>
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <vector>
#include <string>
#include <algorithm>
#include "MinHook.h"

static const uintptr_t RVA_TICK = 0x3a01c0, RVA_PLAY = 0x3a2ad0, RVA_LOOKUP = 0x4ae320,
                       RVA_REGISTRY = 0x4f9c70, RVA_SM = 0x5be2520, RVA_CRC = 0x2a26ef0;
static const uint8_t SIG_TICK[]   = {0x40,0x55,0x53,0x56,0x57,0x41,0x54,0x41,0x55,0x41,0x56,0x41};
static const uint8_t SIG_PLAY[]   = {0x40,0x53,0x48,0x83,0xec,0x20,0x48,0x8b,0xd9,0x48,0x85,0xc9};
static const uint8_t SIG_LOOKUP[] = {0x48,0x89,0x5c,0x24,0x08,0x48,0x89,0x74,0x24,0x10,0x57,0x48};
static const uint8_t SIG_REG[]    = {0x48,0x83,0xec,0x28,0x48,0x8b,0x05,0x2d,0x75,0x6e,0x05,0x48};

typedef void  (*TickFn)();
typedef void  (*PlayFn)(void* obj);
typedef void* (*LookupFn)(uint32_t* id);
typedef void* (*RegistryFn)();

static uintptr_t g_base; static TickFn g_origTick; static PlayFn g_play; static LookupFn g_lookup; static RegistryFn g_registry;
static FILE* g_log;
struct Cin { uint32_t id; std::string name; };
static std::vector<Cin> g_list; static int g_sel = 0;

static void Log(const char* f, ...) {
  if (!g_log) return;
  va_list a; va_start(a, f); vfprintf(g_log, f, a); va_end(a); fputc('\n', g_log); fflush(g_log);
}

// The game's name hash: CRC32 table lookup, init 0, no final xor, ASCII-lowercased.
static uint32_t CrcLower(const char* s) {
  const uint32_t* t = (const uint32_t*)(g_base + RVA_CRC); uint32_t c = 0;
  for (; *s; ++s) { uint8_t ch = (uint8_t)*s; if (ch >= 'A' && ch <= 'Z') ch += 0x20; c = t[(ch ^ c) & 0xff] ^ (c >> 8); }
  return c;
}

static const char* ObjName(uint8_t* o) { return (o[0x31] & 2) ? *(const char**)(o + 8) : (const char*)(o + 8); }

struct RawCin { uint32_t id, key; char name[128]; };
static RawCin g_raw[4096];

// POD only: __try cannot coexist with C++ objects needing unwinding.
static int ReadRegistry() {
  int cnt = 0;
  __try {
    uint8_t* reg = (uint8_t*)g_registry();
    if (!reg) return -1;
    uint32_t n = *(uint32_t*)(reg + 0x38);
    uint32_t* keys = *(uint32_t**)(reg + 0x18); uint64_t* vals = *(uint64_t**)(reg + 0x20);
    Log("registry %p count=%u keys=%p vals=%p", reg, n, keys, vals);
    if (!keys || !vals || n > 4096) return -2;
    for (uint32_t i = 0; i < n; ++i) {
      uint8_t* o = (uint8_t*)vals[i]; if (!o) continue;
      RawCin& c = g_raw[cnt++]; c.id = *(uint32_t*)(o + 0x34); c.key = keys[i];
      const char* nm = ObjName(o); size_t l = nm ? strnlen(nm, 127) : 0;
      memcpy(c.name, nm ? nm : "", l); c.name[l] = 0;
    }
  } __except (EXCEPTION_EXECUTE_HANDLER) { return -3; }
  return cnt;
}

static void BuildList() {
  g_list.clear();
  int n = ReadRegistry();
  if (n < 0) Log("ReadRegistry failed: %d", n);
  for (int i = 0; i < n; ++i) {
    if (g_raw[i].key != g_raw[i].id) Log("note: key %08x != id %08x for %s", g_raw[i].key, g_raw[i].id, g_raw[i].name);
    g_list.push_back({g_raw[i].id, g_raw[i].name});
  }
  std::sort(g_list.begin(), g_list.end(), [](const Cin& a, const Cin& b) { return a.name < b.name; });
  Log("built list: %zu cinematics", g_list.size());
  for (auto& c : g_list) Log("  %08x %s", c.id, c.name.c_str());
}

struct WndCtx { DWORD pid; HWND w; };
static BOOL CALLBACK EnumProc(HWND h, LPARAM l) {
  auto* c = (WndCtx*)l; DWORD p; GetWindowThreadProcessId(h, &p);
  if (p == c->pid && IsWindowVisible(h) && GetWindow(h, GW_OWNER) == nullptr) { c->w = h; return FALSE; }
  return TRUE;
}

// Feedback: window title + beep + log (the game has no overlay we can use yet).
static void Show() {
  char buf[256];
  if (g_list.empty()) snprintf(buf, sizeof buf, "Saints Row  [Replay: no cinematics found]");
  else snprintf(buf, sizeof buf, "Saints Row  [Replay %d/%zu: %s]", g_sel + 1, g_list.size(), g_list[g_sel].name.c_str());
  WndCtx ctx{GetCurrentProcessId(), nullptr};
  EnumWindows(EnumProc, (LPARAM)&ctx);
  if (ctx.w) SetWindowTextA(ctx.w, buf);
  Log("%s", buf); MessageBeep(MB_OK);
}

static bool Edge(int vk) { static bool prev[256]; bool d = (GetAsyncKeyState(vk) & 0x8000) != 0; bool e = d && !prev[vk]; prev[vk] = d; return e; }

static void DoPlay() {
  if (g_list.empty()) return;
  uint8_t* sm = *(uint8_t**)(g_base + RVA_SM);
  if (!sm) { Log("state machine not ready"); return; }
  uint8_t state = **(uint8_t**)(sm + 8);
  if (state != 0) { Log("cinematic system busy (state %u)", state); return; }
  uint32_t id = g_list[g_sel].id; void* obj = g_lookup(&id);
  Log("play %s id=%08x obj=%p", g_list[g_sel].name.c_str(), id, obj);
  if (obj) g_play(obj);
}

static void Hotkeys() {
  int n = (int)g_list.size();
  if (Edge(VK_F7)) { if (!n) BuildList(); n = (int)g_list.size(); if (n) g_sel = (g_sel + n - 1) % n; Show(); }
  if (Edge(VK_F8)) { if (!n) BuildList(); n = (int)g_list.size(); if (n) g_sel = (g_sel + 1) % n; Show(); }
  if (Edge(VK_F6)) { BuildList(); g_sel = 0; Show(); }
  if (Edge(VK_F9)) DoPlay();
}

static void HookedTick() {
  __try { Hotkeys(); } __except (EXCEPTION_EXECUTE_HANDLER) { Log("exception in hotkey handler"); }
  g_origTick();
}

static bool Match(uintptr_t rva, const uint8_t* sig, size_t n) { return memcmp((void*)(g_base + rva), sig, n) == 0; }

static DWORD WINAPI Init(LPVOID) {
  char dir[MAX_PATH]; GetModuleFileNameA(nullptr, dir, MAX_PATH);
  std::string p = dir; p = p.substr(0, p.find_last_of("\\/") + 1) + "sr2022_replay.log"; g_log = fopen(p.c_str(), "w");
  g_base = (uintptr_t)GetModuleHandleA(nullptr);
  auto* nt = (IMAGE_NT_HEADERS*)(g_base + ((IMAGE_DOS_HEADER*)g_base)->e_lfanew);
  Log("replay mod init, base=%p sizeOfImage=%x", (void*)g_base, (unsigned)nt->OptionalHeader.SizeOfImage);
  if (nt->OptionalHeader.SizeOfImage != 0x5f6a000 || !Match(RVA_TICK, SIG_TICK, sizeof SIG_TICK) || !Match(RVA_PLAY, SIG_PLAY, sizeof SIG_PLAY) ||
      !Match(RVA_LOOKUP, SIG_LOOKUP, sizeof SIG_LOOKUP) || !Match(RVA_REGISTRY, SIG_REG, sizeof SIG_REG)) {
    Log("unsupported exe build (only SaintsRow_DX12.exe is supported); mod disabled"); return 0;
  }
  { std::string nh = dir; nh = nh.substr(0, nh.find_last_of("\\/") + 1) + "sr2022_nohook.txt";
    if (GetFileAttributesA(nh.c_str()) != INVALID_FILE_ATTRIBUTES) { Log("sr2022_nohook.txt present: proxy only, no hook"); return 0; } }
  g_play = (PlayFn)(g_base + RVA_PLAY); g_lookup = (LookupFn)(g_base + RVA_LOOKUP); g_registry = (RegistryFn)(g_base + RVA_REGISTRY);
  if (MH_Initialize() != MH_OK) { Log("MH_Initialize failed"); return 0; }
  if (MH_CreateHook((void*)(g_base + RVA_TICK), (void*)HookedTick, (void**)&g_origTick) != MH_OK ||
      MH_EnableHook((void*)(g_base + RVA_TICK)) != MH_OK) { Log("hook failed"); return 0; }
  Log("hooked tick; F6 refresh list, F7/F8 select, F9 play");
  return 0;
}

// ---- dinput8 proxy ----
typedef HRESULT(WINAPI* DI8Create)(HINSTANCE, DWORD, REFIID, LPVOID*, LPUNKNOWN);
extern "C" HRESULT WINAPI DirectInput8Create(HINSTANCE h, DWORD v, REFIID r, LPVOID* o, LPUNKNOWN u) {
  static DI8Create fn = nullptr;
  if (!fn) {
    char sys[MAX_PATH]; GetSystemDirectoryA(sys, MAX_PATH); strcat(sys, "\\dinput8.dll");
    HMODULE m = LoadLibraryA(sys); if (m) fn = (DI8Create)GetProcAddress(m, "DirectInput8Create");
  }
  return fn ? fn(h, v, r, o, u) : E_FAIL;
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID) {
  if (reason == DLL_PROCESS_ATTACH) {
    DisableThreadLibraryCalls(h);
    char exe[MAX_PATH]; GetModuleFileNameA(nullptr, exe, MAX_PATH);
    const char* b = strrchr(exe, '\\'); b = b ? b + 1 : exe;
    if (_strnicmp(b, "SaintsRow", 9) == 0 && _stricmp(b, "SRLauncher.exe") != 0) CreateThread(nullptr, 0, Init, nullptr, 0, nullptr);
  }
  return TRUE;
}
