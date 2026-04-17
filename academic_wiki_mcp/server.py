from academic_wiki_mcp import mcp
# from academic_wiki_mcp.tools import download, discovery  # noqa: F401


def main():
    import sys
    transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
