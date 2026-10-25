/* The SDK's cellPad with keyboard and mouse added to pad port 0.
 *
 * Off Windows the SDK reads controllers only (its keyboard fallback is
 * Windows-only), so without a controller the title sees no pad. This file
 * compiles the SDK's cellPad.c unchanged except for its one controller poll,
 * pad_poll_sdl2(), whose call is routed to port_pad_poll(): the controller is
 * read as before, then keyboard and mouse are merged into port 0, which then
 * counts as connected. A controller and the keyboard work side by side.
 *
 *   W A S D           left stick (move)       Space, K     CROSS (jump)
 *   mouse             right stick (camera)    mouse left, J   SQUARE
 *   arrow keys        d-pad                   mouse right, I  TRIANGLE
 *   Q, E              L1, R1                  mouse middle, L CIRCLE
 *   Left Shift, R     L2, R2                  Enter        CIRCLE (confirm)
 *   V, C              L3, R3                  Backspace    CROSS (back)
 *   Esc               START                   Tab          SELECT
 *
 * The mouse drives the camera while the window has captured it (a click in
 * the window, or fullscreen; Alt or leaving the window releases it), handled
 * in vulkan_bridge.c, which feeds motion and buttons in here.
 * PORT_MOUSE_SENSITIVITY scales the camera (default 1.0: about 1000 pixels a
 * second of mouse motion is a full stick). PAD_NO_KEYBOARD=1 turns keyboard
 * and mouse off, as for scripted test input. */
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
    static float sens = -1.0f, vx, vy;
    static unsigned long long last;
    if (sens < 0) {
        const char* e = getenv("PORT_MOUSE_SENSITIVITY");
        sens = e ? (float)atof(e) : 1.0f;
        if (!(sens > 0.0f)) sens = 1.0f;
    }
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
        vy = (float)dy / (float)dt * sens;
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

    const Uint8* k = SDL_GetKeyboardState(NULL);
    const int focused = k && SDL_GetKeyboardFocus() != NULL;
    static const struct { SDL_Scancode key; u16 btn; } map[] = {
        { SDL_SCANCODE_UP, CELL_PAD_CTRL_UP },         { SDL_SCANCODE_DOWN, CELL_PAD_CTRL_DOWN },
        { SDL_SCANCODE_LEFT, CELL_PAD_CTRL_LEFT },     { SDL_SCANCODE_RIGHT, CELL_PAD_CTRL_RIGHT },
        { SDL_SCANCODE_SPACE, CELL_PAD_CTRL_CROSS },   { SDL_SCANCODE_K, CELL_PAD_CTRL_CROSS },
        { SDL_SCANCODE_BACKSPACE, CELL_PAD_CTRL_CROSS },
        { SDL_SCANCODE_J, CELL_PAD_CTRL_SQUARE },      { SDL_SCANCODE_I, CELL_PAD_CTRL_TRIANGLE },
        { SDL_SCANCODE_L, CELL_PAD_CTRL_CIRCLE },      { SDL_SCANCODE_RETURN, CELL_PAD_CTRL_CIRCLE },
        { SDL_SCANCODE_KP_ENTER, CELL_PAD_CTRL_CIRCLE },
        { SDL_SCANCODE_Q, CELL_PAD_CTRL_L1 },          { SDL_SCANCODE_E, CELL_PAD_CTRL_R1 },
        { SDL_SCANCODE_LSHIFT, CELL_PAD_CTRL_L2 },     { SDL_SCANCODE_R, CELL_PAD_CTRL_R2 },
        { SDL_SCANCODE_V, CELL_PAD_CTRL_L3 },          { SDL_SCANCODE_C, CELL_PAD_CTRL_R3 },
        { SDL_SCANCODE_ESCAPE, CELL_PAD_CTRL_START },  { SDL_SCANCODE_TAB, CELL_PAD_CTRL_SELECT },
    };
    u16 btns = 0;
    float lx = 0.0f, ly = 0.0f;
    if (focused) {
        for (unsigned i = 0; i < sizeof map / sizeof map[0]; i++)
            if (k[map[i].key]) btns |= map[i].btn;
        /* Alt+Enter is the fullscreen toggle, not a confirm. */
        if ((k[SDL_SCANCODE_LALT] || k[SDL_SCANCODE_RALT]) && k[SDL_SCANCODE_RETURN]) btns &= (u16)~CELL_PAD_CTRL_CIRCLE;
        lx = (float)(k[SDL_SCANCODE_D] - k[SDL_SCANCODE_A]);
        ly = (float)(k[SDL_SCANCODE_S] - k[SDL_SCANCODE_W]);
        if (lx && ly) { lx *= 0.7071f; ly *= 0.7071f; }
    }
    if (port_mouse_captured) {
        const int mb = __atomic_load_n(&port_mouse_buttons, __ATOMIC_RELAXED);
        if (mb & SDL_BUTTON_LMASK) btns |= CELL_PAD_CTRL_SQUARE;
        if (mb & SDL_BUTTON_RMASK) btns |= CELL_PAD_CTRL_TRIANGLE;
        if (mb & SDL_BUTTON_MMASK) btns |= CELL_PAD_CTRL_CIRCLE;
    }
    float rx, ry;
    port_mouse_stick(&rx, &ry);

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
