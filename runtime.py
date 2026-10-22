"""Portable runtime paths. Set environment variables in your service or shell."""
import os,pathlib,shutil,sys
ROOT=pathlib.Path(__file__).resolve().parent
ORIGIN=os.environ.get('STUDIO_ORIGIN','https://studio.example.com').rstrip('/')
NODE=os.environ.get('NODE_BIN') or shutil.which('node') or 'node'
CODEX=os.environ.get('CODEX_BIN') or shutil.which('codex') or 'codex'
PYTHON=sys.executable
SKILLS=pathlib.Path(os.environ.get('CODEX_HOME',str(pathlib.Path.home()/'.codex')))/'skills'
NEWS_FETCHER=os.environ.get('NEWS_FETCHER',str(SKILLS/'news-aggregator-skill/scripts/fetch_news.py'))
WIKI_OUTPUT=pathlib.Path(os.environ.get('WIKI_OUTPUT',str(ROOT/'site/wiki')))
IMAGE_BASE=os.environ.get('IMAGE_HOST_BASE','').rstrip('/')+'/'
