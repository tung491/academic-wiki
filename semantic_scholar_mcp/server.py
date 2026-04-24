from semantic_scholar_mcp import mcp
from semantic_scholar_mcp.tools import discovery  # noqa: F401 - registers tools


def main():
    import sys
    transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
