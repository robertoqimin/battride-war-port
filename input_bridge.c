/* The SDK's cellPad with keyboard and mouse added to pad port 0.
 *
 * Off Windows the SDK reads controllers only (its keyboard fallback is
 * Windows-only), so without a controller the title sees no pad. This file
 * compiles the SDK's cellPad.c unchanged except for its one controller poll,
 * pad_poll_sdl2(), whose call is routed to port_pad_poll(): the controller is
 * read as before, then keyboard and mouse are merged into port 0, which then
 * counts as connected. A controller and the keyboard work side by side.
 *
 * Bindings (defaults in s_actions below) can be replaced by a controls file,
 * PORT_CONTROLS=<file>, one control per line:
 *
 *   # comment
 *   square = Mouse Left, J
 *   move_up = W
 *   mouse_sensitivity = 1.0
 *   invert_y = 0
 *
 * Keys are SDL key names (W, Space, Left Shift, Return, Up, Keypad 8, F5...),
 * resolved to the key at that position in the current layout; mouse buttons
 * are Mouse Left, Mouse Right, Mouse Middle, Mouse X1 and Mouse X2. A control
 * the file leaves out keeps its default; an empty value unbinds it.
 *
 * The mouse drives the camera while the window has captured it (a click in
 * the window, or fullscreen; Alt or leaving the window releases it), handled
 * in vulkan_bridge.c, which feeds motion and buttons in here.
 * mouse_sensitivity scales the camera (1.0: about 1000 pixels a second of
 * motion is a full stick); PORT_MOUSE_SENSITIVITY overrides it. PAD_NO_KEYBOARD=1
 * turns keyboard and mouse off, as for scripted test input. */
#include <SDL2/SDL.h>

static void port_pad_poll(void);
/* `static void pad_poll_sdl2(void)` becomes the SDK's own poll under a new
 * name; the call `pad_poll_sdl2()` becomes port_pad_poll(). */
#define PORT_PAD_POLL_void port_sdk_pad_poll_sdl2(void)
#define PORT_PAD_POLL_     port_pad_poll()
#define PORT_PAD_POLL_PICK(arg) PORT_PAD_POLL_##arg
#define pad_poll_sdl2(...) PORT_PAD_POLL_PICK(__VA_ARGS__)
#include PORT_CELLPAD_SOURCE
#undef pad_poll_sdl2

/* Mouse state from the window's event pump (vulkan_bridge.c). */
int port_mouse_captured;          /* relative mode on: motion is camera   */
int port_mouse_buttons;           /* SDL_BUTTON_LMASK etc. while captured */
static int s_mouse_dx, s_mouse_dy;

void port_input_mouse_motion(int dx, int dy)
{
    __atomic_add_fetch(&s_mouse_dx, dx, __ATOMIC_RELAXED);
    __atomic_add_fetch(&s_mouse_dy, dy, __ATOMIC_RELAXED);
}

int port_input_keyboard_enabled(void)
{
    static int on = -1;
    if (on < 0) on = getenv("PAD_NO_KEYBOARD") ? 0 : 1;
    return on;
}

/* What each control is bound to. A stick direction has no pad bit. */
enum { STICK_NONE, MOVE_UP, MOVE_DOWN, MOVE_LEFT, MOVE_RIGHT, CAM_UP, CAM_DOWN, CAM_LEFT, CAM_RIGHT };
#define PORT_MAX_BINDS 6
static struct {
    const char* name;
    u16 btn;
    int stick;
    const char* defaults;
    int n, code[PORT_MAX_BINDS];   /* >= 0 a scancode, < 0 -(SDL mouse button) */
} s_actions[] = {
    { "move_up",      0, MOVE_UP,    "W" },
    { "move_down",    0, MOVE_DOWN,  "S" },
    { "move_left",    0, MOVE_LEFT,  "A" },
    { "move_right",   0, MOVE_RIGHT, "D" },
    { "camera_up",    0, CAM_UP,     "" },
    { "camera_down",  0, CAM_DOWN,   "" },
    { "camera_left",  0, CAM_LEFT,   "" },
    { "camera_right", 0, CAM_RIGHT,  "" },
    { "square",   CELL_PAD_CTRL_SQUARE,   STICK_NONE, "Mouse Left, J" },
    { "triangle", CELL_PAD_CTRL_TRIANGLE, STICK_NONE, "Mouse Right, I" },
    { "circle",   CELL_PAD_CTRL_CIRCLE,   STICK_NONE, "Mouse Middle, L, Return, Keypad Enter" },
    { "cross",    CELL_PAD_CTRL_CROSS,    STICK_NONE, "Space, K, Backspace" },
    { "l1",       CELL_PAD_CTRL_L1,       STICK_NONE, "Q" },
    { "r1",       CELL_PAD_CTRL_R1,       STICK_NONE, "E" },
    { "l2",       CELL_PAD_CTRL_L2,       STICK_NONE, "Left Shift" },
    { "r2",       CELL_PAD_CTRL_R2,       STICK_NONE, "R" },
    { "l3",       CELL_PAD_CTRL_L3,       STICK_NONE, "V" },
    { "r3",       CELL_PAD_CTRL_R3,       STICK_NONE, "C" },
    { "up",       CELL_PAD_CTRL_UP,       STICK_NONE, "Up" },
    { "down",     CELL_PAD_CTRL_DOWN,     STICK_NONE, "Down" },
    { "left",     CELL_PAD_CTRL_LEFT,     STICK_NONE, "Left" },
    { "right",    CELL_PAD_CTRL_RIGHT,    STICK_NONE, "Right" },
    { "start",    CELL_PAD_CTRL_START,    STICK_NONE, "Escape" },
    { "select",   CELL_PAD_CTRL_SELECT,   STICK_NONE, "Tab" },
};
#define PORT_ACTIONS (sizeof s_actions / sizeof s_actions[0])
static float s_sensitivity = 1.0f;
static int s_invert_y;

static int port_input_code(const char* name)
{
    static const char* mouse[] = { "Mouse Left", "Mouse Middle", "Mouse Right", "Mouse X1", "Mouse X2" };
    for (int b = 0; b < 5; b++)
        if (!SDL_strcasecmp(name, mouse[b])) return -(b + 1);   /* SDL_BUTTON_LEFT.. */
    SDL_Scancode sc = SDL_GetScancodeFromKey(SDL_GetKeyFromName(name));
    if (sc == SDL_SCANCODE_UNKNOWN) sc = SDL_GetScancodeFromName(name);
    if (sc == SDL_SCANCODE_UNKNOWN) {
        printf("[cellPad] controls: unknown key '%s'\n", name);
        return 0;                                  /* 0 = SDL_SCANCODE_UNKNOWN, never pressed */
    }
    return (int)sc;
}

static void port_input_bind(unsigned a, const char* list)
{
    s_actions[a].n = 0;
    char buf[256];
    SDL_strlcpy(buf, list, sizeof buf);
    for (char* tok = strtok(buf, ","); tok && s_actions[a].n < PORT_MAX_BINDS; tok = strtok(NULL, ",")) {
        while (*tok == ' ' || *tok == '\t') tok++;
        char* end = tok + strlen(tok);
        while (end > tok && (end[-1] == ' ' || end[-1] == '\t' || end[-1] == '\r' || end[-1] == '\n')) *--end = '\0';
        if (*tok) s_actions[a].code[s_actions[a].n++] = port_input_code(tok);
    }
}

/* Defaults, then the controls file. Needs SDL's video subsystem (the key
 * layout), so it runs on the first poll, after the window exists. */
static void port_input_load(void)
{
    for (unsigned a = 0; a < PORT_ACTIONS; a++) port_input_bind(a, s_actions[a].defaults);
    const char* path = getenv("PORT_CONTROLS");
    FILE* f = path && *path ? fopen(path, "r") : NULL;
    if (f) {
        char line[512];
        while (fgets(line, sizeof line, f)) {
            char* eq = strchr(line, '=');
            if (line[0] == '#' || !eq) continue;
            *eq = '\0';
            char* key = line;
            while (*key == ' ' || *key == '\t') key++;
            char* kend = key + strlen(key);
            while (kend > key && (kend[-1] == ' ' || kend[-1] == '\t')) *--kend = '\0';
            const char* value = eq + 1;
            if (!strcmp(key, "mouse_sensitivity")) { s_sensitivity = (float)atof(value); continue; }
            if (!strcmp(key, "invert_y")) { s_invert_y = atoi(value) != 0; continue; }
            for (unsigned a = 0; a < PORT_ACTIONS; a++)
                if (!strcmp(key, s_actions[a].name)) port_input_bind(a, value);
        }
        fclose(f);
        printf("[cellPad] controls from %s\n", path);
    }
    const char* e = getenv("PORT_MOUSE_SENSITIVITY");
    if (e) s_sensitivity = (float)atof(e);
    if (!(s_sensitivity > 0.0f) || s_sensitivity > 20.0f) s_sensitivity = 1.0f;
}

static int port_input_down(unsigned a, const Uint8* keys, int mouse)
{
    for (int i = 0; i < s_actions[a].n; i++) {
        const int c = s_actions[a].code[i];
        if (c > 0 ? (keys && keys[c]) : (c < 0 && (mouse & SDL_BUTTON(-c)))) return 1;
    }
    return 0;
}

static u8 port_stick(float v)    /* -1..1 to 0..255, centre 128 */
{
    int x = 128 + (int)(v * 127.0f + (v < 0 ? -0.5f : 0.5f));
    return (u8)(x < 0 ? 0 : x > 255 ? 255 : x);
}

/* Mouse motion to a right-stick deflection: speed in pixels per millisecond,
 * scaled, held briefly between motion events so a poll faster than the mouse
 * reports does not flicker the camera back to centre. */
static void port_mouse_stick(float* rx, float* ry)
{
    static float vx, vy;
    static unsigned long long last;
    const float sens = s_sensitivity;
    const unsigned long long now = pad_now_ms();
    unsigned long long dt = last ? now - last : 16;
    last = now;
    if (dt < 1) dt = 1;
    if (dt > 50) dt = 50;
    const int dx = __atomic_exchange_n(&s_mouse_dx, 0, __ATOMIC_RELAXED);
    const int dy = __atomic_exchange_n(&s_mouse_dy, 0, __ATOMIC_RELAXED);
    if (!port_mouse_captured) { vx = vy = 0.0f; *rx = *ry = 0.0f; return; }
    if (dx || dy) {
        vx = (float)dx / (float)dt * sens;
        vy = (float)dy / (float)dt * sens * (s_invert_y ? -1.0f : 1.0f);
    } else {
        vx *= 0.5f; vy *= 0.5f;   /* motion stopped: settle within a few polls */
    }
    *rx = vx < -1.0f ? -1.0f : vx > 1.0f ? 1.0f : vx;
    *ry = vy < -1.0f ? -1.0f : vy > 1.0f ? 1.0f : vy;
}

static void port_pad_poll(void)
{
    port_sdk_pad_poll_sdl2();
    if (!port_input_keyboard_enabled()) return;

    static int loaded;
    if (!loaded) { port_input_load(); loaded = 1; }
    const Uint8* k = SDL_GetKeyboardState(NULL);
    const int focused = k && SDL_GetKeyboardFocus() != NULL;
    const int mouse = port_mouse_captured ? __atomic_load_n(&port_mouse_buttons, __ATOMIC_RELAXED) : 0;
    const Uint8* keys = focused ? k : NULL;
    u16 btns = 0;
    float lx = 0.0f, ly = 0.0f, kx = 0.0f, ky = 0.0f;
    for (unsigned a = 0; a < PORT_ACTIONS; a++) {
        if (!port_input_down(a, keys, mouse)) continue;
        switch (s_actions[a].stick) {
        case MOVE_UP: ly -= 1.0f; break;    case MOVE_DOWN: ly += 1.0f; break;
        case MOVE_LEFT: lx -= 1.0f; break;  case MOVE_RIGHT: lx += 1.0f; break;
        case CAM_UP: ky -= 1.0f; break;     case CAM_DOWN: ky += 1.0f; break;
        case CAM_LEFT: kx -= 1.0f; break;   case CAM_RIGHT: kx += 1.0f; break;
        default: btns |= s_actions[a].btn;
        }
    }
    /* Alt+Enter is the fullscreen toggle, not a press of what Enter is bound to. */
    if (keys && (keys[SDL_SCANCODE_LALT] || keys[SDL_SCANCODE_RALT]) && keys[SDL_SCANCODE_RETURN]) {
        for (unsigned a = 0; a < PORT_ACTIONS; a++)
            for (int i = 0; i < s_actions[a].n; i++)
                if (s_actions[a].code[i] == SDL_SCANCODE_RETURN) btns &= (u16)~s_actions[a].btn;
    }
    if (lx && ly) { lx *= 0.7071f; ly *= 0.7071f; }
    if (kx && ky) { kx *= 0.7071f; ky *= 0.7071f; }
    float rx, ry;
    port_mouse_stick(&rx, &ry);
    if (kx || ky) { rx = kx; ry = ky; }          /* camera keys win over the mouse */

    PadHostState* hs = &s_host_state[0];
    if (!hs->connected) {               /* keyboard only: a neutral pad to merge into */
        memset(hs, 0, sizeof *hs);
        hs->analog_lx = hs->analog_ly = hs->analog_rx = hs->analog_ry = 128;
        hs->connected = 1;
        static int said;
        if (!said++) printf("[cellPad] keyboard and mouse on port 0\n");
    }
    hs->buttons |= btns;
    if (lx || ly) { hs->analog_lx = port_stick(lx); hs->analog_ly = port_stick(ly); }
    if (rx || ry) { hs->analog_rx = port_stick(rx); hs->analog_ry = port_stick(ry); }
    if (btns & CELL_PAD_CTRL_L2) hs->trigger_l2 = 255;
    if (btns & CELL_PAD_CTRL_R2) hs->trigger_r2 = 255;
    const u16 all = hs->buttons;
    if (all & CELL_PAD_CTRL_UP)       hs->press_up = 255;
    if (all & CELL_PAD_CTRL_DOWN)     hs->press_down = 255;
    if (all & CELL_PAD_CTRL_LEFT)     hs->press_left = 255;
    if (all & CELL_PAD_CTRL_RIGHT)    hs->press_right = 255;
    if (all & CELL_PAD_CTRL_TRIANGLE) hs->press_triangle = 255;
    if (all & CELL_PAD_CTRL_CIRCLE)   hs->press_circle = 255;
    if (all & CELL_PAD_CTRL_CROSS)    hs->press_cross = 255;
    if (all & CELL_PAD_CTRL_SQUARE)   hs->press_square = 255;
    if (all & CELL_PAD_CTRL_L1)       hs->press_l1 = 255;
    if (all & CELL_PAD_CTRL_R1)       hs->press_r1 = 255;
}
