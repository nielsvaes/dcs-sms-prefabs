"""Standalone test: derive() flattens meta.required_modules into the index."""
import lua_prefab

SRC = '''return {
  meta = {
    name = "Herc pair",
    required_modules = {
      ["UH-60L"] = { id = "UH-60L", display_name = "UH-60L Black Hawk",
                     objects = { ["UH-60L"] = 2, ["KC130J"] = 1 }, count = 3 },
      ["A-4E-C"] = { id = "A-4E-C", display_name = "A-4E-C",
                     objects = { ["A-4E-C"] = 1 }, count = 1 },
    },
  },
  groups = {}, statics = {}, zones = {}, drawings = {},
}'''

def main():
    parsed = lua_prefab.parse(SRC)
    d = lua_prefab.derive(parsed)
    rm = d["required_modules"]
    assert isinstance(rm, list), rm
    assert len(rm) == 2, rm
    assert rm[0]["id"] == "A-4E-C", rm
    assert rm[1]["id"] == "UH-60L", rm
    assert rm[1]["display_name"] == "UH-60L Black Hawk", rm
    assert rm[1]["count"] == 3, rm
    empty = lua_prefab.derive(lua_prefab.parse('return { meta = { name = "x" }, groups = {} }'))
    assert empty["required_modules"] == [], empty
    print("OK test_required_modules")

if __name__ == "__main__":
    main()
