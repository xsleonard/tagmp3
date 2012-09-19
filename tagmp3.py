#!/usr/bin/env python

import argparse
import os
import sys
import re
import string
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, ID3NoHeaderError, TIT2
from mutagen.easyid3 import EasyID3
from datetime import datetime

title_token = '<title>'
artist_token = '<artist>'
album_token = '<album>'
year_token = '<year>'
trackno_token = '<trackno>'

_tokens = [title_token, artist_token, year_token, trackno_token, album_token]

def get_args():
    p = argparse.ArgumentParser(description='Tag mp3 files using filenames.  All files must have the same naming scheme.')
    p.add_argument('source_dir', help='source directory containing files')
    p.add_argument('--artist', default='', help='artist name override')
    p.add_argument('--album', default='', help='album name override')
    p.add_argument('--year', type=int, default=datetime.now().year, help='year override')
    p.add_argument('--genre', type=str, default='')
    p.add_argument('--delimiter', '-d', default='-', help="""
            Delimiter between format tags.
            Limitation: the delimiter must not be in any of the token names.
            Whitespace around tokens is ignored,
            So the delimiter does not need to include it,
            except to avoid collisions with token names""")
    p.add_argument('--various-artists', '-va', action='store_true', help='When guessing format, if the artist names are not the same for all tracks, don\'t switch to %s assumption' % trackno_token)
    p.add_argument('--guess-trackno', '-gt', action='store_true', help='If <trackno> not found in filenames, apply a guessed trackno (alphabetical)')
    p.add_argument('--trackno-format', '-tf', default='%d', help='string format specificier for guessed track number tag strings. Is ignored if --guess-trackno is not enabled')
    p.add_argument('--ignore-no-title', '-int', action='store_true', help='If no title is in the format, or no title found for filename, add tags anyway. By default, the program will skip that file.')
    p.add_argument('--preserve-tags', '-pt', action='store_true', help='The program will wipe all existing tags if you do not enable this. Note: if a new value for a tag is parsed from the filename, it will still overwrite existing tag names')
    p.add_argument('--format', default='', help="""
        Filename format override. Keywords are <artist> <title> <album> <trackno>
        Default filename format search order:
        <artist> - <title>
        If <artist> is not constant for all files, try
        <trackno> - <title>
        <trackno> must be convertible to an integer in this case
        If --artist is provided, assumes <trackno> - <title> also
        If no delimiter found, assumes <title> regardless, and won't add track number tags,
        unless --guess-trackno is enable
        Tokens are: %s
    """ % (', '.join(_tokens)))
    
    args = p.parse_args()

    if not os.path.exists(args.source_dir):
        print "%s not found" % args.source_dir
        sys.exit(1)

    if not os.path.isdir(args.source_dir):
        print "%s is not a directory" % args.source_dir
        sys.exit(1)

    if not os.listdir(args.source_dir):
        print "No files found in %s" % args.source_dir
        sys.exit(1)        
        
    args.format = args.format.lower()
    cre = re.compile('(<[a-z]+>)')
    tokens = set(cre.findall(args.format))
    if not tokens.issubset(set(_tokens)):
        print "Unrecognized tokens found in --format:"
        print  "\t", ', '.join(tokens.difference(set(_tokens)))
        sys.exit(1)
        
    return args


def decide_artist_or_trackno(files, delim, various_artists):
    ret_token = artist_token
    first_token_matches = True
    first = False
    token = ''
    for f in files:
        f = f.rstrip('.mp3')
        if f.count(delim) != 1:
            return ''   # Neither
        if not various_artists:
            _token = f.split(delim)[0].strip()
            if not first:
                first = True
                token = _token
                continue
            if token != _token:
                ret_token = trackno_token
                break

    # Check if trackno is integers
    if ret_token == trackno_token:
        for f in files:
            f = f.rstrip('.mp3')
            try:
                int(f.split(delim)[0])
            except ValueError:
                return ''
    
    return ret_token
    

def guess_format(f, delim, artist_or_trackno):
    if not artist_or_trackno:
        return ''
        
    fmt = title_token
    if delim in f:
        fmt = '{1}{0}{2}'.format(delim, artist_or_trackno, title_token)

    return fmt
    

def filenames_consistent(files, fmt, delim):
    fmt_delim_ct = fmt.count(delim)
    ct = -1
    for f in files:
        _ct = f.count(delim)
        if fmt and _ct != fmt_delim_ct:
            print "Format does not match files"
            return False
        if ct < 0:
            ct = _ct
        elif ct != _ct:
            return False
    return True


def get_token_values(n, f, artist_or_trackno):
    if not f.endswith('.mp3'):
        return
    f = f.split('.')[0]

    # guess format from filename
    fmt = args.format
    if not fmt:
        fmt = guess_format(f, args.delimiter, artist_token)
    if not fmt:
        print "Could not guess format for file: %s" % (f + '.mp3')
        return

    if not args.ignore_no_title and title_token not in fmt:
        print "No title token found in format %s for file %s. Cannot guess title" % (fmt, f + '.mp3')

    # extract data using tokens
    fmtp = map(string.strip, fmt.split(args.delimiter))
    fp = map(string.strip, f.split(args.delimiter))
    fplen = len(fp)

    try:
        title_index = fmtp.index(title_token)
    except ValueError:
        if not args.ignore_no_title:
            print "WARNING: No title found for file: %s" % (f + '.mp3')
            return
    try:
        artist_index = fmtp.index(artist_token)
    except ValueError:
        artist_index = None
    try:
        album_index = fmtp.index(album_token)
    except ValueError:
        album_index = None
    try:
        year_index = fmtp.index(year_token)
    except ValueError:
        year_index = None
    try:
        trackno_index = fmtp.index(trackno_token)
    except ValueError:
        trackno_index = None

    title = fp[title_index]
    artist = args.artist
    if not artist and artist_index is not None:
        artist = fp[artist_index]
    album = args.album
    if not album and album_index is not None:
        album = fp[album_index]
    year = args.year
    if not year and year_index is not None:
        year = fp[year_index]
    trackno = ''
    if trackno_index is not None:
        trackno = fp[trackno_index]
    elif args.guess_trackno:
        trackno = args.trackno_format % (n + 1)

    return dict(artist=artist, album=album, title=title, year=year, trackno=trackno)


def write_tags(f, preserve_tags, artist='', album='', title='', year='', trackno='', genre=''):
    print "Track Number: {4}, Artist: {0}, Album: {1}, Title: {2}, Year: {3}, Genre: {5}".format(artist, album, title, year, trackno, genre)

    # remove existing tags
    if not preserve_tags:
        try:
            tags = ID3(f)
            tags.delete()
        except ID3NoHeaderError:
            pass

    # open tags 
    try:
        tags = EasyID3(f)
    except ID3NoHeaderError:
        tags = MP3(f, ID3=EasyID3)
        tags.add_tags(ID3=EasyID3)

    tags['artist'] = unicode(artist)
    tags['album'] = unicode(album)
    tags['title'] = unicode(title)
    tags['date'] = unicode(year)
    tags['tracknumber'] = unicode(trackno)
    tags['genre'] = unicode(genre)
    tags.save()

            
def tag_files(args):
    files = os.listdir(args.source_dir)
    files = filter(lambda a: a.lower().endswith('.mp3'), files)
    files.sort()

    if not filenames_consistent(files, args.format, args.delimiter):
        print "Filenames are not consistent."
        sys.exit(1)

    artist_or_trackno = ''
    if not args.format:
        artist_or_trackno = decide_artist_or_trackno(files, args.delimiter, args.various_artists)
    
    for i, f in enumerate(files):
        token_vals = get_token_values(i, f, artist_or_trackno)
        if token_vals is None:
            continue
        write_tags(os.path.join(args.source_dir, f), args.preserve_tags, genre=args.genre, **token_vals)


if __name__ == '__main__':
    args = get_args()
    tag_files(args)
