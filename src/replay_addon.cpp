// SR2022 Cutscene Replay: ReShade add-on. Hooks the game's cinematic tick (game thread), reads the game's own
// cinematic registry, and replays a chosen cinematic through the game's own "cinematic_play" path.
// UI: ReShade overlay tab "Cutscene Replay" (Home key) + numpad hotkeys.
// Offsets are for SaintsRow_DX12.exe (SizeOfImage 0x5f6a000); prologues are verified before hooking.
#include <windows.h>
#include <cstdarg>
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <vector>
#include <string>
#include <algorithm>
#include <atomic>
#include <imgui.h>
#include <reshade.hpp>
#include "MinHook.h"

static const uintptr_t RVA_TICK = 0x3a01c0, RVA_PLAY = 0x3a2ad0, RVA_LOOKUP = 0x4ae320, RVA_SKIP = 0x3a1d90,
                       RVA_REGISTRY = 0x4f9c70, RVA_SM = 0x5be2520, RVA_CRC = 0x2a26ef0;
static const uint8_t SIG_TICK[]   = {0x40,0x55,0x53,0x56,0x57,0x41,0x54,0x41,0x55,0x41,0x56,0x41};
static const uint8_t SIG_PLAY[]   = {0x40,0x53,0x48,0x83,0xec,0x20,0x48,0x8b,0xd9,0x48,0x85,0xc9};
static const uint8_t SIG_LOOKUP[] = {0x48,0x89,0x5c,0x24,0x08,0x48,0x89,0x74,0x24,0x10,0x57,0x48};
static const uint8_t SIG_REG[]    = {0x48,0x83,0xec,0x28,0x48,0x8b,0x05,0x2d,0x75,0x6e,0x05,0x48};

typedef void  (*TickFn)();
typedef void  (*PlayFn)(void* obj);
typedef void* (*LookupFn)(uint32_t* id);
typedef void* (*RegistryFn)();
typedef void  (*SkipFn)();

static uintptr_t g_base; static TickFn g_origTick; static PlayFn g_play; static LookupFn g_lookup; static RegistryFn g_registry; static SkipFn g_skip;
static FILE* g_log;
struct Cin { uint32_t id; std::string name; };
static std::vector<Cin> g_list;          // written only on the game thread (inside the tick hook)
static std::atomic<int> g_listVersion{0};
static std::atomic<int> g_reqPlay{-1};   // index into g_list, requested by UI/hotkey
static std::atomic<bool> g_reqRefresh{true}, g_reqSkip{false}, g_reqScan{false};
static std::atomic<int> g_state{-1};     // last seen cinematic state byte
static std::string g_status = "waiting for the game to load...";
static int g_sel = 0;

static void Log(const char* f, ...) {
  if (!g_log) return;
  va_list a; va_start(a, f); vfprintf(g_log, f, a); va_end(a); fputc('\n', g_log); fflush(g_log);
}

struct RawCin { uint32_t id, key; char name[128]; };
static RawCin g_raw[4096];
static const char* ObjName(uint8_t* o) { return (o[0x31] & 2) ? *(const char**)(o + 8) : (const char*)(o + 8); }

// POD only: __try cannot coexist with C++ objects needing unwinding.
static int ReadRegistry() {
  int cnt = 0;
  __try {
    uint8_t* reg = (uint8_t*)g_registry();
    if (!reg) return -1;
    uint32_t n = *(uint32_t*)(reg + 0x38);
    uint32_t* keys = *(uint32_t**)(reg + 0x18); uint64_t* vals = *(uint64_t**)(reg + 0x20);
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
  for (int i = 0; i < n; ++i) g_list.push_back({g_raw[i].id, g_raw[i].name});
  std::sort(g_list.begin(), g_list.end(), [](const Cin& a, const Cin& b) { return a.name < b.name; });
  Log("built list: %zu cinematics", g_list.size());
  g_listVersion++;
}

static bool Edge(int vk) { static bool prev[256]; bool d = (GetAsyncKeyState(vk) & 0x8000) != 0; bool e = d && !prev[vk]; prev[vk] = d; return e; }

static void DoPlay(int idx) {
  if (idx < 0 || idx >= (int)g_list.size()) return;
  uint8_t* sm = *(uint8_t**)(g_base + RVA_SM);
  if (!sm) { g_status = "cinematic system not ready"; return; }
  uint8_t state = **(uint8_t**)(sm + 8);
  if (state != 0) { g_status = "busy (a cinematic is already running or loading) - use Cancel"; Log("busy, state %u", state); return; }
  uint32_t id = g_list[idx].id; void* obj = g_lookup(&id);
  Log("play %s id=%08x obj=%p", g_list[idx].name.c_str(), id, obj);
  g_status = "playing " + g_list[idx].name;
  if (obj) g_play(obj); else g_status = "lookup failed for " + g_list[idx].name;
}


// ---- diagnostic: is a given string present in the game's memory? (numpad 7) ----
// Used to find out whether patched phone Lua (data\sr_vanguard\...\vdo_phone.lua) was actually loaded.
// RPAT is the pattern stored REVERSED, so no forward copy of it exists in this process (a forward temp would match itself).
static size_t ScanFor(const std::string& rpat, std::vector<uintptr_t>& hits) {
  SYSTEM_INFO si; GetSystemInfo(&si);
  const size_t n_pat = rpat.size(); const char first = rpat[n_pat - 1];
  uint8_t* a = (uint8_t*)si.lpMinimumApplicationAddress; size_t total = 0;
  while (a < (uint8_t*)si.lpMaximumApplicationAddress) {
    MEMORY_BASIC_INFORMATION mbi;
    if (!VirtualQuery(a, &mbi, sizeof mbi)) break;
    uint8_t* next = (uint8_t*)mbi.BaseAddress + mbi.RegionSize;
    bool ok = mbi.State == MEM_COMMIT && !(mbi.Protect & (PAGE_GUARD | PAGE_NOACCESS | PAGE_WRITECOMBINE)) && mbi.Type != MEM_IMAGE;
    if (ok) {
      const char* s = (const char*)mbi.BaseAddress; size_t n = mbi.RegionSize; total += n;
      __try {
        for (size_t i = 0; i + n_pat <= n; ++i) {
          const char* f = (const char*)memchr(s + i, first, n - n_pat + 1 - i);
          if (!f) break;
          i = f - s;
          bool m = true; for (size_t k = 0; k < n_pat && m; ++k) m = f[k] == rpat[n_pat - 1 - k];
          if (m && hits.size() < 8) hits.push_back((uintptr_t)f);
        }
      } __except (EXCEPTION_EXECUTE_HANDLER) {}
    }
    if (next <= a) break;
    a = next;
  }
  return total;
}

static void LogContext(uintptr_t addr) {
  char buf[161]; size_t k = 0;
  __try { const char* s = (const char*)addr - 40; for (; k < 160; ++k) { char c = s[k]; buf[k] = (c >= 32 && c < 127) ? c : '.'; } } __except (EXCEPTION_EXECUTE_HANDLER) {}
  buf[k] = 0; Log("   %p: %s", (void*)addr, buf);
}

static std::atomic<bool> g_scanning{false};
static void StartScan();
static DWORD WINAPI ScanThread(LPVOID) {
  Log("scan started"); DWORD t0 = GetTickCount();
  // Patterns are assembled at runtime so this binary's own string constants do not match.
  // reversed patterns: marker comment from the patched Lua, a patched identifier, and an unpatched control
  const std::string pats[] = { "PPA_YALPER_2202RS", "YALPER_ENOHP", "ofni_etats_metsys_etadpu" };
  const char* labels[] = { "patched marker comment", "patched PHONE_REPLAY state", "UNPATCHED control (update_system_state_info)" };
  int li = 0;
  for (const auto& rp : pats) {
    const char* label = labels[li++];
    std::vector<uintptr_t> hits; size_t scanned = ScanFor(rp, hits);
    Log("scan [%s]: %zu hit(s) in %zu MB (%u ms)", label, hits.size(), scanned >> 20, (unsigned)(GetTickCount() - t0));
    for (auto h : hits) LogContext(h);
  }
  Log("scan done (expected if patched Lua is loaded: phone_replay_app and Replay a mission > 0; controls update_system_state_info / cheat_app_on_select > 0 if Lua text is resident)");
  g_status = "memory scan done, see sr2022_replay.log";
  g_scanning = false;
  return 0;
}

static void StartScan() {
  if (g_scanning.exchange(true)) return;
  g_status = "scanning memory...";
  Log("scan requested");
  CreateThread(nullptr, 0, ScanThread, nullptr, 0, nullptr);
}

static void Hotkeys() {
  int n = (int)g_list.size();
  if (Edge(VK_NUMPAD1)) g_reqRefresh = true;
  if (Edge(VK_NUMPAD4) && n) { g_sel = (g_sel + n - 1) % n; MessageBeep(MB_OK); }
  if (Edge(VK_NUMPAD6) && n) { g_sel = (g_sel + 1) % n; MessageBeep(MB_OK); }
  if (Edge(VK_NUMPAD5) && n) g_reqPlay = g_sel;
  if (Edge(VK_NUMPAD0)) g_reqSkip = true;
  if (Edge(VK_NUMPAD7)) StartScan();
  { static ULONGLONG t0 = GetTickCount64(); static int auto_n = 0;  // also scan on its own at +40/80/120 s
    if (auto_n < 3 && GetTickCount64() - t0 > 40000ull + 40000ull * auto_n) { ++auto_n; Log("auto scan %d", auto_n); StartScan(); } }
}

static void Process() {  // game thread
  Hotkeys();
  uint8_t* sm = *(uint8_t**)(g_base + RVA_SM);
  g_state = sm ? (int)**(uint8_t**)(sm + 8) : -1;
  if (g_reqRefresh.exchange(false)) { BuildList(); if (g_sel >= (int)g_list.size()) g_sel = 0; if (g_status.rfind("waiting", 0) == 0) g_status = "ready"; }
  if (g_reqScan.exchange(false)) StartScan();
  if (g_reqSkip.exchange(false)) { Log("skip/cancel requested (state %d)", (int)g_state); g_skip(); g_status = "cancel requested"; }
  int p = g_reqPlay.exchange(-1);
  if (p >= 0) DoPlay(p);
}

static void HookedTick() {
  __try { Process(); } __except (EXCEPTION_EXECUTE_HANDLER) { Log("exception in Process()"); }
  g_origTick();
}

// ---- ReShade overlay (render thread: only reads g_list snapshot by version, sets request flags) ----
static bool g_showAll = false; static char g_filter[64] = "";
static std::vector<Cin> g_uiList; static int g_uiVersion = -1;

static bool Hidden(const std::string& n) { return n == "cin_default" || n == "cin_default_city" || n == "cin3d_beep_test" || n == "cin3d_announce_screenshot_01"; }

static void DrawOverlay(reshade::api::effect_runtime*) {
  if (g_uiVersion != g_listVersion) { g_uiList = g_list; g_uiVersion = g_listVersion; }
  ImGui::TextWrapped("Replay a story cutscene. Play offline, in the open world (not during a mission). If it hangs, press Cancel.");
  ImGui::Text("State: %s   |   %s", g_state == 0 ? "idle" : (g_state < 0 ? "n/a" : "cinematic busy"), g_status.c_str());
  if (ImGui::Button("Refresh list")) g_reqRefresh = true;
  ImGui::SameLine(); if (ImGui::Button("Cancel / skip")) g_reqSkip = true;
  ImGui::SameLine(); ImGui::Checkbox("show test/default", &g_showAll);
  ImGui::SameLine(); if (ImGui::Button("Scan memory (diag)")) g_reqScan = true;
  ImGui::InputText("filter", g_filter, sizeof g_filter);
  ImGui::Text("Numpad: 4/6 select, 5 play, 0 cancel, 1 refresh. Selected: %s",
              (g_sel >= 0 && g_sel < (int)g_list.size()) ? g_list[g_sel].name.c_str() : "-");
  ImGui::BeginChild("cinlist", ImVec2(0, 360), true);
  std::string f = g_filter; std::transform(f.begin(), f.end(), f.begin(), [](unsigned char c) { return (char)tolower(c); });
  for (size_t i = 0; i < g_uiList.size(); ++i) {
    const Cin& c = g_uiList[i];
    if (!g_showAll && Hidden(c.name)) continue;
    if (!f.empty() && c.name.find(f) == std::string::npos) continue;
    ImGui::PushID((int)i);
    if (ImGui::Button("Play")) { g_sel = (int)i; g_reqPlay = (int)i; }
    ImGui::SameLine();
    if (ImGui::Selectable(c.name.c_str(), g_sel == (int)i)) g_sel = (int)i;
    ImGui::PopID();
  }
  ImGui::EndChild();
}


// ---- diagnostic: which parts of sr_vanguard.vpp_pc does the game read? (phone documents: original vs patched copy) ----
// Matches on the file offset for ANY handle (the streaming handle may predate our hooks), logs the handle's path, and also
// logs file mappings of the archive in case it is memory-mapped instead of read.
struct IoRange { const char* name; uint64_t start, size; };
static const IoRange kRanges[] = {
  {"phone ORIGINAL", 0xd6fe47beull, 2288576}, {"phone PATCHED", 0x1e5a42b3full, 2404798},
  {"cheat ORIGINAL", 0xd3f03ff4ull, 744576},  {"cheat PATCHED", 0x1e5c8dcfdull, 760405},
};
typedef LONG (NTAPI *NtReadFileFn)(HANDLE, HANDLE, PVOID, PVOID, PVOID /*IO_STATUS_BLOCK*/, PVOID, ULONG, PLARGE_INTEGER, PULONG);
typedef HANDLE (WINAPI *CreateFileAFn)(LPCSTR, DWORD, DWORD, LPSECURITY_ATTRIBUTES, DWORD, DWORD, HANDLE);
typedef HANDLE (WINAPI *CreateFileWFn)(LPCWSTR, DWORD, DWORD, LPSECURITY_ATTRIBUTES, DWORD, DWORD, HANDLE);
typedef BOOL (WINAPI *CloseHandleFn)(HANDLE);
typedef HANDLE (WINAPI *CreateMappingWFn)(HANDLE, LPSECURITY_ATTRIBUTES, DWORD, DWORD, DWORD, LPCWSTR);
typedef LPVOID (WINAPI *MapViewFn)(HANDLE, DWORD, DWORD, DWORD, SIZE_T);
static NtReadFileFn g_origNtRead; static CreateFileAFn g_origCreateA; static CreateFileWFn g_origCreateW; static CloseHandleFn g_origClose;
static CreateMappingWFn g_origMapping; static MapViewFn g_origMapView;
static std::atomic<int> g_ioLogged{0}, g_ioGeneral{0}, g_mapLogged{0};
static std::atomic<HANDLE> g_vanguard[16];  // open handles of sr_vanguard.vpp_pc
static std::atomic<HANDLE> g_vanguardMap[8];  // file-mapping objects created from them
static bool IsIn(std::atomic<HANDLE>* arr, int n, HANDLE h) { for (int i = 0; i < n; ++i) if (arr[i].load() == h) return true; return false; }
static bool IsVanguard(HANDLE h) { return IsIn(g_vanguard, 16, h); }
static void Track(std::atomic<HANDLE>* arr, int n, HANDLE h) { for (int i = 0; i < n; ++i) { HANDLE e = nullptr; if (arr[i].compare_exchange_strong(e, h)) break; } }
static std::string HandlePath(HANDLE h) {
  char b[512]; DWORD n = GetFinalPathNameByHandleA(h, b, sizeof b, FILE_NAME_NORMALIZED);
  return (n && n < sizeof b) ? std::string(b) : std::string("?");
}
static HANDLE WINAPI HookedCreateFileA(LPCSTR n, DWORD a, DWORD s, LPSECURITY_ATTRIBUTES sa, DWORD d, DWORD f, HANDLE t) {
  HANDLE h = g_origCreateA(n, a, s, sa, d, f, t);
  if (h != INVALID_HANDLE_VALUE && n && strstr(n, "sr_vanguard.vpp")) {
    Log("open(A) %s handle=%p access=%08x flags=%08x", n, h, a, f);
    Track(g_vanguard, 16, h);
  }
  return h;
}
static HANDLE WINAPI HookedCreateFileW(LPCWSTR n, DWORD a, DWORD s, LPSECURITY_ATTRIBUTES sa, DWORD d, DWORD f, HANDLE t) {
  HANDLE h = g_origCreateW(n, a, s, sa, d, f, t);
  if (h != INVALID_HANDLE_VALUE && n && wcsstr(n, L"sr_vanguard.vpp")) {
    Log("open(W) %ls handle=%p access=%08x flags=%08x", n, h, a, f);
    Track(g_vanguard, 16, h);
  }
  return h;
}
static BOOL WINAPI HookedCloseHandle(HANDLE h) {
  for (auto& v : g_vanguard) { HANDLE e = h; if (v.compare_exchange_strong(e, nullptr)) Log("close vanguard handle=%p", h); }
  for (auto& v : g_vanguardMap) { HANDLE e = h; v.compare_exchange_strong(e, nullptr); }
  return g_origClose(h);
}
static HANDLE WINAPI HookedCreateMappingW(HANDLE f, LPSECURITY_ATTRIBUTES sa, DWORD prot, DWORD hi, DWORD lo, LPCWSTR name) {
  HANDLE m = g_origMapping(f, sa, prot, hi, lo, name);
  if (m && f && f != INVALID_HANDLE_VALUE) {
    std::string path = HandlePath(f);
    if (IsVanguard(f) || path.find("sr_vanguard.vpp") != std::string::npos) {
      Log("MAPPING of %s: mapping=%p prot=%x size=%llx", path.c_str(), m, prot, ((unsigned long long)hi << 32) | lo);
      Track(g_vanguardMap, 8, m);
    }
  }
  return m;
}
static LPVOID WINAPI HookedMapView(HANDLE m, DWORD access, DWORD offHi, DWORD offLo, SIZE_T bytes) {
  LPVOID p = g_origMapView(m, access, offHi, offLo, bytes);
  if (p && IsIn(g_vanguardMap, 8, m) && g_mapLogged < 200) {
    ++g_mapLogged;
    Log("MAP VIEW of vanguard: off=%llx bytes=%llx -> %p", ((unsigned long long)offHi << 32) | offLo, (unsigned long long)bytes, p);
  }
  return p;
}
static LONG NTAPI HookedNtReadFile(HANDLE h, HANDLE ev, PVOID apc, PVOID apcCtx, PVOID iosb, PVOID buf, ULONG n, PLARGE_INTEGER byteOff, PULONG key) {
  if (g_ioLogged < 120) {
    bool known = IsVanguard(h);
    uint64_t off = ~0ull;
    if (byteOff && byteOff->QuadPart >= 0) off = (uint64_t)byteOff->QuadPart;
    else if (known) { LARGE_INTEGER z{}, pos{}; if (SetFilePointerEx(h, z, &pos, FILE_CURRENT)) off = (uint64_t)pos.QuadPart; }
    const IoRange* hit = nullptr;
    for (const auto& r : kRanges) if (off != ~0ull && off < r.start + r.size && off + n > r.start) { hit = &r; break; }
    if (hit) {  // any handle: offsets this high only occur in the multi-GB archives
      ++g_ioLogged; Log("IO read %s: off=%llx len=%u handle=%p tracked=%d %s", hit->name, (unsigned long long)off, n, h, (int)known, known ? "" : HandlePath(h).c_str());
    } else if (known && g_ioGeneral < 25) { ++g_ioGeneral; Log("IO vanguard read: off=%llx len=%u", (unsigned long long)off, n); }
  }
  return g_origNtRead(h, ev, apc, apcCtx, iosb, buf, n, byteOff, key);
}

static bool Match(uintptr_t rva, const uint8_t* sig, size_t n) { return memcmp((void*)(g_base + rva), sig, n) == 0; }

static DWORD WINAPI Init(LPVOID) {
  char dir[MAX_PATH]; GetModuleFileNameA(nullptr, dir, MAX_PATH);
  std::string p = dir; p = p.substr(0, p.find_last_of("\\/") + 1) + "sr2022_replay.log"; g_log = fopen(p.c_str(), "w");
  g_base = (uintptr_t)GetModuleHandleA(nullptr);
  auto* nt = (IMAGE_NT_HEADERS*)(g_base + ((IMAGE_DOS_HEADER*)g_base)->e_lfanew);
  Log("replay mod init, base=%p sizeOfImage=%x", (void*)g_base, (unsigned)nt->OptionalHeader.SizeOfImage);
  Log("exe: %s", dir);
  if (nt->OptionalHeader.SizeOfImage != 0x5f6a000) { Log("unsupported exe build (only SaintsRow_DX12.exe is supported); mod disabled"); return 0; }
  // ReShade loads add-ons very early; wait for the game code to be in its final state before checking/hooking.
  bool ok = false;
  for (int i = 0; i < 600 && !ok; ++i) {
    ok = Match(RVA_TICK, SIG_TICK, sizeof SIG_TICK) && Match(RVA_PLAY, SIG_PLAY, sizeof SIG_PLAY) &&
         Match(RVA_LOOKUP, SIG_LOOKUP, sizeof SIG_LOOKUP) && Match(RVA_REGISTRY, SIG_REG, sizeof SIG_REG);
    if (!ok) { if (i % 20 == 0) { const uint8_t* t = (const uint8_t*)(g_base + RVA_TICK); Log("waiting for code, tick bytes %02x %02x %02x %02x", t[0], t[1], t[2], t[3]); } Sleep(500); }
  }
  if (!ok) { Log("signatures never matched; mod disabled"); return 0; }
  { MH_STATUS ms = MH_Initialize(); if (ms != MH_OK) Log("MH_Initialize: %d", (int)ms); }
  { void* nt = (void*)GetProcAddress(GetModuleHandleA("ntdll.dll"), "NtReadFile");
    if (nt && MH_CreateHook(nt, (void*)HookedNtReadFile, (void**)&g_origNtRead) == MH_OK && MH_EnableHook(nt) == MH_OK) Log("hooked NtReadFile (diag)"); else Log("NtReadFile hook failed"); }
  { void* ca = (void*)CreateFileA; void* cw = (void*)CreateFileW; void* ch = (void*)CloseHandle;
    void* cm = (void*)CreateFileMappingW; void* mv = (void*)MapViewOfFile;
    bool ok = MH_CreateHook(ca, (void*)HookedCreateFileA, (void**)&g_origCreateA) == MH_OK && MH_EnableHook(ca) == MH_OK &&
              MH_CreateHook(cw, (void*)HookedCreateFileW, (void**)&g_origCreateW) == MH_OK && MH_EnableHook(cw) == MH_OK &&
              MH_CreateHook(ch, (void*)HookedCloseHandle, (void**)&g_origClose) == MH_OK && MH_EnableHook(ch) == MH_OK &&
              MH_CreateHook(cm, (void*)HookedCreateMappingW, (void**)&g_origMapping) == MH_OK && MH_EnableHook(cm) == MH_OK &&
              MH_CreateHook(mv, (void*)HookedMapView, (void**)&g_origMapView) == MH_OK && MH_EnableHook(mv) == MH_OK;
    Log(ok ? "hooked CreateFileA/W, CloseHandle, CreateFileMappingW, MapViewOfFile (diag)" : "file API hooks failed (diag)"); }
  for (int i = 0; i < 1200 && !*(uintptr_t*)(g_base + RVA_SM); ++i) Sleep(500);  // cinematic state machine exists once a world is up
  Log("signatures ok, cinematic system %s", *(uintptr_t*)(g_base + RVA_SM) ? "ready" : "not ready (hooking anyway)");
  g_play = (PlayFn)(g_base + RVA_PLAY); g_lookup = (LookupFn)(g_base + RVA_LOOKUP); g_registry = (RegistryFn)(g_base + RVA_REGISTRY); g_skip = (SkipFn)(g_base + RVA_SKIP);
  if (MH_CreateHook((void*)(g_base + RVA_TICK), (void*)HookedTick, (void**)&g_origTick) != MH_OK ||
      MH_EnableHook((void*)(g_base + RVA_TICK)) != MH_OK) { Log("hook failed"); return 0; }
  Log("hooked tick; numpad 1 refresh, 4/6 select, 5 play, 0 cancel; overlay tab 'Cutscene Replay'");
  return 0;
}

// ---- ReShade add-on scaffolding (loaded by the ReShade already in the game folder) ----
extern "C" __declspec(dllexport) const char* NAME = "SR2022 Cutscene Replay";
extern "C" __declspec(dllexport) const char* DESCRIPTION = "Replay story cinematics from a ReShade overlay tab or numpad keys (SaintsRow_DX12.exe only).";

BOOL APIENTRY DllMain(HMODULE h, DWORD reason, LPVOID) {
  if (reason == DLL_PROCESS_ATTACH) {
    char exe[MAX_PATH]; GetModuleFileNameA(nullptr, exe, MAX_PATH);
    const char* b = strrchr(exe, '\\'); b = b ? b + 1 : exe;
    if (_strnicmp(b, "SaintsRow", 9) != 0) return TRUE;  // launcher etc.: stay inert
    // register_addon also binds ImGui; if ReShade's ImGui version differs it returns false, in which case we run without the overlay.
    bool ui = reshade::register_addon(h);
    // ReShade may load/unload add-on files (probing, reloads). Our worker thread must never outlive the module:
    // pin it, and only let the first loaded instance start the hook.
    HMODULE pinned; GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_PIN | GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS, (LPCSTR)&DllMain, &pinned);
    HANDLE once = CreateMutexA(nullptr, FALSE, "Local\\sr2022_replay_once");
    if (once && GetLastError() == ERROR_ALREADY_EXISTS) return TRUE;
    if (ui) reshade::register_overlay("Cutscene Replay", DrawOverlay);
    CreateThread(nullptr, 0, Init, nullptr, 0, nullptr);
  } else if (reason == DLL_PROCESS_DETACH) {
    reshade::unregister_addon(h);
  }
  return TRUE;
}
