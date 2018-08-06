#!/usr/bin/env python3

# Based on code by Stephan Sokolow
# Source: https://gist.github.com/ssokolow/e7c9aae63fb7973e4d64cff969a78ae8
"""python-xlib example which reacts to changing the active window/title.
 - requires python-xlib.

intend to give a clickable display of x11 clients as a tree.
potentially a replacement for tree style tabs outside of firefox
e.g. use with uzbl or vimb
see
  pstree -sp $(xprop _NET_WM_PID |cut -f2 -d=)
  xwininfo -root -tree
  xlsclients
"""

from contextlib import contextmanager
import Xlib
import Xlib.display
import psutil

# Connect to the X server and get the root window
disp = Xlib.display.Display()
root = disp.screen().root

# Prepare the property names we use so they can be fed into X11 APIs
NET_ACTIVE_WINDOW = disp.intern_atom('_NET_ACTIVE_WINDOW')
NET_WM_NAME = disp.intern_atom('_NET_WM_NAME')  # UTF-8
WM_NAME = disp.intern_atom('WM_NAME')           # Legacy encoding

WM_PID = disp.intern_atom('_NET_WM_PID')

last_seen = {'xid': None, 'title': None, 'pid': None}
prev_seen = last_seen


@contextmanager
def window_obj(win_id):
    """Simplify dealing with BadWindow (make it either valid or None)"""
    window_obj = None
    if win_id:
        try:
            window_obj = disp.create_resource_object('window', win_id)
        except Xlib.error.XError:
            pass
    yield window_obj


def get_active_window():
    """Return a (window_obj, focus_has_changed) tuple for the active window."""
    win_id = root.get_full_property(NET_ACTIVE_WINDOW,
                                    Xlib.X.AnyPropertyType).value[0]

    focus_changed = (win_id != last_seen['xid'])
    if focus_changed:
        with window_obj(last_seen['xid']) as old_win:
            if old_win:
                old_win.change_attributes(event_mask=Xlib.X.NoEventMask)

        last_seen['xid'] = win_id
        with window_obj(win_id) as new_win:
            if new_win:
                new_win.change_attributes(event_mask=Xlib.X.PropertyChangeMask)

    return win_id, focus_changed


def _get_window_name_inner(win_obj):
    """Simplify dealing with _NET_WM_NAME (UTF-8) vs. WM_NAME (legacy)"""
    for atom in (NET_WM_NAME, WM_NAME, WM_PID):
        try:
            window_name = win_obj.get_full_property(atom, 0)
        except UnicodeDecodeError:  # Apparently a Debian distro package bug
            title = "<could not decode characters>"
        else:
            if window_name:
                win_name = window_name.value
                if isinstance(win_name, bytes):
                    # Apparently COMPOUND_TEXT is so arcane that this is how
                    # tools like xprop deal with receiving it these days
                    win_name = win_name.decode('latin1', 'replace')
                return win_name
            else:
                title = "<unnamed window>"

    return "{} (XID: {})".format(title, win_obj.id)


def get_window_name(win_id):
    """Look up the window name for a given X11 window ID"""
    global prev_seen, last_seen
    win_title = None

    # never hit
    # if not win_id:
    #     last_seen['title'] = "<no window id>"
    #     return last_seen['title']

    title_changed = False
    with window_obj(win_id) as wobj:
        if wobj:
            win_title = _get_window_name_inner(wobj)
            title_changed = (win_title != last_seen['title'])

    if title_changed:
        prev_seen = last_seen
        last_seen['title'] = win_title
        last_seen['pid'] = int(wobj.get_full_property(WM_PID, 0).value[0])

    return last_seen['title'], title_changed


def handle_xevent(event):
    # Loop through, ignoring events until we're notified of focus/title change
    if event.type != Xlib.X.PropertyNotify:
        return

    changed = False
    if event.atom == NET_ACTIVE_WINDOW:
        if get_active_window()[1]:   # if window focus has changed
            changed = changed or get_window_name(last_seen['xid'])[1]
    elif event.atom in (NET_WM_NAME, WM_NAME):
        changed = changed or get_window_name(last_seen['xid'])[1]

    if changed:
        handle_change(last_seen, prev_seen)


def handle_change(new_state, prev_state):
    """Replace this with whatever you want to actually do"""
    closed = not psutil.pid_exists(prev_state['pid'])  # close or change focus
    print(closed)
    print(new_state)


if __name__ == '__main__':
    # Listen for _NET_ACTIVE_WINDOW changes
    root.change_attributes(event_mask=Xlib.X.PropertyChangeMask)

    # Prime last_seen with whatever window was active when we started this
    get_window_name(get_active_window()[0])
    handle_change(last_seen, prev_seen)

    while True:  # next_event() sleeps until we get an event
        handle_xevent(disp.next_event())
