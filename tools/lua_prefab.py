"""lua_prefab.py — parse-don't-execute loader for untrusted .prefab files.

A faithful Python port of the Mission-Editor client's
`prefab_safe_load.lua`. It tokenises Lua source and parses ONLY the data
subset:

    return <table>

where <table> contains string / number / true / false / nil literals,
nested tables, and keys (bare identifier, ["str"], [num], [true]/[false],
or positional). Anything else — function calls, identifiers-as-values,
operators, function defs, varargs, extra statements, `/` (hence NaN/inf
written as 0/0, 1/0), `==`, ... — is REJECTED without execution.

This is the security keystone of the catalog repo: the same grammar the
in-DCS client enforces before it will adopt a downloaded prefab. CI runs
it on every `.prefab` so a non-data file can never reach `main`.

Public API:
    parse(src)        -> dict                  (raises PrefabError)
    parse_file(path)  -> dict                  (raises PrefabError)
    derive(parsed)    -> dict of derived fields (counts / theatre / ...)

Tables are represented as Python dicts; positional values get integer keys
starting at 1, exactly like Lua. Use array_len()/array_values() to walk the
array part.
"""

import io


class PrefabError(Exception):
    """Raised when a source is not a pure-data prefab. `pos` is a 1-based
    character offset into the source (0 if unknown)."""

    def __init__(self, msg, pos=0):
        super().__init__("safe-load rejected (pos %d): %s" % (pos, msg))
        self.msg = msg
        self.pos = pos


# --- Lexer ------------------------------------------------------------------
# Token kinds: 'punct' (one of { } [ ] = , ;), 'string', 'number',
#              'true', 'false', 'nil', 'return', 'name', 'eof'.
# Comments and whitespace are skipped. Any disallowed character/sequence
# (operators, parens, etc.) raises PrefabError.

_KEYWORDS = {"return", "true", "false", "nil"}

_ESCAPES = {
    "n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b",
    "f": "\f", "v": "\v", "\\": "\\", '"': '"', "'": "'", "\n": "\n",
}


def _is_digit(c):
    return c != "" and c.isdigit() and c.isascii()


def _is_hex(c):
    return c != "" and c in "0123456789abcdefABCDEF"


def _is_name_start(c):
    return c != "" and (c == "_" or (c.isalpha() and c.isascii()))


def _is_name_part(c):
    return c != "" and (c == "_" or (c.isalnum() and c.isascii()))


def _lex(src):
    tokens = []
    i, n = 0, len(src)  # i is a 0-based index; pos reported as i+1 (1-based)

    def at(j):
        return src[j] if 0 <= j < n else ""

    def long_bracket(start):
        # start points at the first '['. Supports [[ ]] and [=[ ]=] levels.
        # Returns (next_index, inner_text) or (None, None) if not a long bracket.
        j = start
        if at(j) != "[":
            return None, None
        j += 1
        level = 0
        while at(j) == "=":
            level += 1
            j += 1
        if at(j) != "[":
            return None, None
        inner_start = j + 1
        close = "]" + ("=" * level) + "]"
        e = src.find(close, inner_start)
        if e == -1:
            raise PrefabError("unterminated long bracket", start + 1)
        return e + len(close), src[inner_start:e]

    while i < n:
        c = src[i]
        if c in " \t\r\n":
            i += 1
        elif c == "-" and at(i + 1) == "-":
            # comment: long or line
            after = i + 2
            if at(after) == "[":
                nxt, _ = long_bracket(after)
                if nxt is not None:
                    i = nxt
                else:
                    e = src.find("\n", after)
                    i = (e + 1) if e != -1 else n
            else:
                e = src.find("\n", after)
                i = (e + 1) if e != -1 else n
        elif c == '"' or c == "'":
            quote = c
            buf = []
            j = i + 1
            while True:
                ch = at(j)
                if ch == "":
                    raise PrefabError("unterminated string", i + 1)
                if ch == quote:
                    j += 1
                    break
                if ch == "\n":
                    raise PrefabError("unterminated string", i + 1)
                if ch == "\\":
                    e = at(j + 1)
                    if e in _ESCAPES:
                        buf.append(_ESCAPES[e])
                        j += 2
                    elif _is_digit(e):
                        digits = ""
                        k = j + 1
                        while len(digits) < 3 and _is_digit(at(k)):
                            digits += at(k)
                            k += 1
                        buf.append(chr(int(digits) % 256))
                        j = j + 1 + len(digits)
                    else:
                        raise PrefabError("invalid string escape \\" + e, j + 1)
                else:
                    buf.append(ch)
                    j += 1
            tokens.append(("string", "".join(buf), i + 1))
            i = j
        elif (
            _is_digit(c)
            or (c == "." and _is_digit(at(i + 1)))
            or (
                c == "-"
                and (_is_digit(at(i + 1)) or (at(i + 1) == "." and _is_digit(at(i + 2))))
            )
        ):
            # number: optional leading '-' sign immediately before a digit or
            # '.digit', then hex or decimal float w/ exponent. A '-' NOT
            # followed by a number falls through to the disallowed-character
            # branch (so binary subtraction is rejected). NO '/' is ever lexed,
            # so NaN/inf serialized as 0/0, 1/0 are rejected (per the format).
            negate = False
            start = i
            if c == "-":
                negate = True
                start = i + 1
            num, end = _match_number(src, start)
            if num is None:
                raise PrefabError("malformed number", i + 1)
            value = num
            if negate:
                value = -value
            tokens.append(("number", value, i + 1))
            i = end
        elif _is_name_start(c):
            j = i + 1
            while _is_name_part(at(j)):
                j += 1
            word = src[i:j]
            if word in _KEYWORDS:
                tokens.append((word, None, i + 1))
            else:
                tokens.append(("name", word, i + 1))
            i = j
        elif c in "{}[]=,;":
            # A lone '[' could start a long-string literal ([[...]]). Support
            # that so string values using long brackets still parse. '=' must
            # be a single '=' (reject '==').
            if c == "[" and at(i + 1) in "[=":
                nxt, text = long_bracket(i)
                if nxt is not None:
                    tokens.append(("string", text, i + 1))
                    i = nxt
                else:
                    tokens.append(("punct", "[", i + 1))
                    i += 1
            elif c == "=" and at(i + 1) == "=":
                raise PrefabError("comparison operator not allowed", i + 1)
            else:
                tokens.append(("punct", c, i + 1))
                i += 1
        else:
            raise PrefabError('disallowed character "%s"' % c, i + 1)

    tokens.append(("eof", None, n + 1))
    return tokens


def _match_number(src, start):
    """Match an unsigned Lua number magnitude at `start`. Returns
    (value, end_index) or (None, start). Mirrors the three ordered patterns
    in prefab_safe_load.lua: hex int, decimal float w/ exponent, decimal."""
    n = len(src)
    # 1) hex integer: 0[xX]%x+
    if src[start : start + 2] in ("0x", "0X"):
        j = start + 2
        if j < n and _is_hex(src[j]):
            while j < n and _is_hex(src[j]):
                j += 1
            return float(int(src[start:j], 16)), j
        return None, start

    # 2) decimal float w/ exponent: %d*%.?%d+[eE][%+%-]?%d+
    # 3) decimal:                   %d*%.?%d+
    j = start
    while j < n and src[j].isdigit():
        j += 1
    if j < n and src[j] == ".":
        j += 1
    frac_start = j
    while j < n and src[j].isdigit():
        j += 1
    # require at least one digit in the mantissa overall
    mant = src[start:j]
    if mant == "" or mant == ".":
        return None, start
    if not any(ch.isdigit() for ch in mant):
        return None, start
    # optional exponent
    k = j
    if k < n and src[k] in "eE":
        k += 1
        if k < n and src[k] in "+-":
            k += 1
        if k < n and src[k].isdigit():
            while k < n and src[k].isdigit():
                k += 1
            j = k
        # if no exponent digits, leave j before the 'e' (it lexes separately
        # and the parser's separator check rejects it)
    try:
        return float(src[start:j]), j
    except ValueError:
        return None, start


# --- Parser -----------------------------------------------------------------

_NIL = object()  # sentinel: a parsed `nil` value (assignment is skipped)


def _normalize_number(v):
    """Lua has only doubles. Normalise integral values to Python int so table
    keys like [1], [2] are ints (clean array iteration); keep true floats."""
    if isinstance(v, float) and v.is_integer():
        # guard against huge values that overflow int conversion meaning
        return int(v)
    return v


def _parse(tokens):
    p = [0]

    def peek():
        return tokens[p[0]]

    def peek2():
        idx = p[0] + 1
        return tokens[idx] if idx < len(tokens) else tokens[-1]

    def advance():
        t = tokens[p[0]]
        p[0] += 1
        return t

    def expect(ty, val=None):
        t = tokens[p[0]]
        if t[0] != ty or (val is not None and t[1] != val):
            want = ty + (' "%s"' % val if val is not None else "")
            raise PrefabError("expected " + want, t[2])
        p[0] += 1
        return t

    def is_punct(t, v):
        return t[0] == "punct" and t[1] == v

    def parse_value():
        """Returns (value, was_nil)."""
        t = peek()
        ty = t[0]
        if ty == "string":
            advance()
            return t[1], False
        if ty == "number":
            advance()
            return _normalize_number(t[1]), False
        if ty == "true":
            advance()
            return True, False
        if ty == "false":
            advance()
            return False, False
        if ty == "nil":
            advance()
            return None, True
        if is_punct(t, "{"):
            return parse_table(), False
        if ty == "name":
            raise PrefabError('identifier "%s" is not a literal value' % t[1], t[2])
        raise PrefabError("unexpected %s where a value was expected" % ty, t[2])

    def parse_table():
        expect("punct", "{")
        tbl = {}
        array_idx = 0
        while True:
            t = peek()
            if is_punct(t, "}"):
                advance()
                break

            if is_punct(t, "["):
                # [ key ] = value   where key is string/number/bool literal
                advance()
                kt = peek()
                if kt[0] == "string" or kt[0] == "number":
                    key = _normalize_number(kt[1]) if kt[0] == "number" else kt[1]
                    advance()
                elif kt[0] == "true":
                    key = True
                    advance()
                elif kt[0] == "false":
                    key = False
                    advance()
                else:
                    raise PrefabError(
                        "table key must be a string/number/boolean literal", kt[2]
                    )
                expect("punct", "]")
                expect("punct", "=")
                v, was_nil = parse_value()
                if not was_nil:
                    tbl[key] = v
            elif t[0] == "name" and is_punct(peek2(), "="):
                # bare identifier key:  name = value
                key = t[1]
                advance()
                advance()  # name, '='
                v, was_nil = parse_value()
                if not was_nil:
                    tbl[key] = v
            else:
                # positional value
                v, was_nil = parse_value()
                array_idx += 1
                if not was_nil:
                    tbl[array_idx] = v

            sep = peek()
            if is_punct(sep, ",") or is_punct(sep, ";"):
                advance()
            elif is_punct(sep, "}"):
                pass  # loop handles close
            else:
                raise PrefabError('expected "," ";" or "}" in table', sep[2])
        return tbl

    expect("return")
    if not is_punct(peek(), "{"):
        raise PrefabError("top-level value must be a table constructor", peek()[2])
    result = parse_table()
    if is_punct(peek(), ";"):
        advance()
    if peek()[0] != "eof":
        raise PrefabError("unexpected trailing content", peek()[2])
    return result


def parse(src):
    """Parse a prefab source string into a Python dict. Raises PrefabError on
    anything that is not a pure-data `return {<table>}`."""
    if not isinstance(src, str):
        raise PrefabError("source must be a string")
    tokens = _lex(src)
    result = _parse(tokens)
    if not isinstance(result, dict):
        raise PrefabError("top-level value is not a table")
    return result


def parse_file(path):
    with io.open(path, "r", encoding="utf-8", newline="") as f:
        return parse(f.read())


# --- Derivation -------------------------------------------------------------
# Mirrors prefab_ops.row_from_prefab / split_group_counts in the main repo,
# so the manifest counts match exactly what the ME library shows.


def array_len(tbl):
    """Length of the array part of a Lua-style table (contiguous int keys
    from 1). Non-dicts / empty tables -> 0."""
    if not isinstance(tbl, dict):
        return 0
    n = 0
    while (n + 1) in tbl:
        n += 1
    return n


def array_values(tbl):
    if not isinstance(tbl, dict):
        return []
    return [tbl[i] for i in range(1, array_len(tbl) + 1)]


def _split_group_counts(groups):
    g = s = 0
    for entry in array_values(groups):
        if isinstance(entry, dict) and entry.get("type") == "static":
            s += 1
        else:
            g += 1
    return g, s


def derive(parsed):
    """Derive the manifest's auto-filled fields from a parsed prefab table.
    Returns a dict: groups, statics, zones, drawings, airbases, theatre,
    place_at_origin, name, created_utc."""
    meta = parsed.get("meta")
    if not isinstance(meta, dict):
        meta = {}
    g_count, s_inline = _split_group_counts(parsed.get("groups"))
    airbases = meta.get("airbases")
    airbase_count = array_len(airbases) if isinstance(airbases, dict) else 0
    theatre = meta.get("theatre")
    name = meta.get("name")
    created = meta.get("created_utc")
    return {
        "name": name if isinstance(name, str) else None,
        "theatre": theatre if isinstance(theatre, str) else "",
        "place_at_origin": meta.get("place_at_origin") is True,
        "groups": g_count,
        "statics": s_inline + array_len(parsed.get("statics")),
        "zones": array_len(parsed.get("zones")),
        "drawings": array_len(parsed.get("drawings")),
        "airbases": airbase_count,
        "created_utc": created if isinstance(created, str) else None,
    }
