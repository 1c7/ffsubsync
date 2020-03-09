# -*- coding: utf-8 -*-
import copy
import logging
import sys
from datetime import timedelta

from sklearn.base import TransformerMixin
import pysubs2
import srt

from .file_utils import open_file

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _preprocess_subs(subs, max_subtitle_seconds=None, start_seconds=0, tolerant=True):
    subs_list = []
    start_time = timedelta(seconds=start_seconds)
    max_duration = timedelta(days=1)
    if max_subtitle_seconds is not None:
        max_duration = timedelta(seconds=max_subtitle_seconds)
    subs = iter(subs)
    while True:
        try:
            next_sub = GenericSubtitle.wrap_inner_subtitle(next(subs))
            if next_sub.start < start_time:
                continue
            next_sub.end = min(next_sub.end, next_sub.start + max_duration)
            subs_list.append(next_sub)
        # We don't catch SRTParseError here b/c that typically raised when we
        # are trying to parse with the wrong encoding, in which case we might
        # be able to try another one on the *entire* set of subtitles elsewhere.
        except ValueError as e:
            if tolerant:
                logger.warning(e)
                continue
            else:
                raise
        except StopIteration:
            break
    return subs_list


class _SubsMixin(object):
    def __init__(self, subs=None):
        self.subs_ = subs

    def set_encoding(self, encoding):
        self.subs_.set_encoding(encoding)
        return self


class GenericSubtitle(object):
    def __init__(self, start, end, inner):
        self.start = start
        self.end = end
        self.inner = inner

    def __eq__(self, other):
        eq = True
        eq = eq and self.start == other.start
        eq = eq and self.end == other.end
        eq = eq and self.inner == other.inner
        return eq

    def resolve_inner_timestamps(self):
        ret = copy.deepcopy(self.inner)
        if isinstance(self.inner, srt.Subtitle):
            ret.start = self.start
            ret.end = self.end
        elif isinstance(self.inner, pysubs2.SSAEvent):
            ret.start = pysubs2.make_time(s=self.start.total_seconds())
            ret.end = pysubs2.make_time(s=self.end.total_seconds())
        else:
            raise NotImplementedError('unsupported subtitle type: %s' % type(self.inner))
        return ret

    @classmethod
    def wrap_inner_subtitle(cls, sub):
        if isinstance(sub, srt.Subtitle):
            return cls(sub.start, sub.end, sub)
        elif isinstance(sub, pysubs2.SSAEvent):
            return cls(
                timedelta(milliseconds=sub.start),
                timedelta(milliseconds=sub.end),
                sub
            )
        else:
            raise NotImplementedError('unsupported subtitle type: %s' % type(sub))


class GenericSubtitlesFile(object):
    def __init__(self, subs, *args, **kwargs):
        format = kwargs.pop('format', None)
        if format is None:
            raise ValueError('format must be specified')
        encoding = kwargs.pop('encoding', None)
        if encoding is None:
            raise ValueError('encoding must be specified')
        self.subs_ = subs
        self._format = format
        self._encoding = encoding

    def set_encoding(self, encoding):
        if encoding != 'same':
            self._encoding = encoding
        return self

    def __len__(self):
        return len(self.subs_)

    def __getitem__(self, item):
        return self.subs_[item]

    @property
    def format(self):
        return self._format

    @property
    def encoding(self):
        return self._encoding

    def gen_raw_resolved_subs(self):
        for sub in self.subs_:
            yield sub.resolve_inner_timestamps()

    def offset(self, td):
        offset_subs = []
        for sub in self.subs_:
            offset_subs.append(
                GenericSubtitle(sub.start + td, sub.end + td, sub.inner)
            )
        return GenericSubtitlesFile(
            offset_subs,
            format=self.format,
            encoding=self.encoding
        )

    def write_file(self, fname):
        subs = list(self.gen_raw_resolved_subs())
        if self.format == 'srt':
            to_write = srt.compose(subs)
        elif self.format in ('ssa', 'ass'):
            ssaf = pysubs2.SSAFile()
            ssaf.events = subs
            to_write = ssaf.to_string(self.format)
        else:
            raise NotImplementedError('unsupported format: %s' % self.format)

        if sys.version_info[0] > 2:
            with open(fname or sys.stdout.fileno(), 'wb', encoding=self.encoding) as f:
                f.write(to_write)
        else:
            with (fname and open(fname, 'wb')) or sys.stdout as f:
                f.write(to_write.encode(self.encoding))


class GenericSubtitleParser(_SubsMixin, TransformerMixin):
    def __init__(self, fmt='srt', encoding='infer', max_subtitle_seconds=None, start_seconds=0):
        super(self.__class__, self).__init__()
        self.format = fmt
        self.encoding_to_use = encoding
        self.sub_skippers = []
        self.max_subtitle_seconds = max_subtitle_seconds
        self.start_seconds = start_seconds

    def fit(self, fname, *_):
        encodings_to_try = (self.encoding_to_use,)
        if self.encoding_to_use == 'infer':
            encodings_to_try = ('utf-8', 'utf-8-sig', 'chinese', 'latin-1', 'utf-16')
        with open_file(fname, 'rb') as f:
            subs = f.read()
        exc = None
        for encoding in encodings_to_try:
            try:
                decoded_subs = subs.decode(encoding).strip()
                if self.format == 'srt':
                    parsed_subs = srt.parse(decoded_subs)
                elif self.format in ('ass', 'ssa'):
                    parsed_subs = pysubs2.SSAFile.from_string(decoded_subs)
                else:
                    raise NotImplementedError('unsupported format: %s' % self.format)
                self.subs_ = GenericSubtitlesFile(
                    _preprocess_subs(parsed_subs,
                                     max_subtitle_seconds=self.max_subtitle_seconds,
                                     start_seconds=self.start_seconds),
                    format=format,
                    encoding=encoding
                )
                return self
            except Exception as e:
                exc = e
                continue
        raise exc

    def transform(self, *_):
        return self.subs_


class SubtitleOffseter(_SubsMixin, TransformerMixin):
    def __init__(self, td_seconds):
        super(_SubsMixin, self).__init__()
        if not isinstance(td_seconds, timedelta):
            self.td_seconds = timedelta(seconds=td_seconds)
        else:
            self.td_seconds = td_seconds

    def fit(self, subs, *_):
        self.subs_ = subs.offset(self.td_seconds)
        return self

    def transform(self, *_):
        return self.subs_


def read_srt_from_file(fname, encoding='infer'):
    return GenericSubtitleParser(encoding).fit_transform(fname)


def write_srt_to_file(fname, subs, encoding):
    return GenericSubtitlesFile(subs, encoding=encoding).write_file(fname)


def subs_offset(subs, td_seconds):
    return SubtitleOffseter(td_seconds).fit_transform(subs)
