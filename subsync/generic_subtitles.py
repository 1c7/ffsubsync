# -*- coding: utf-8 -*-
import copy
from datetime import timedelta
import logging

import pysubs2
import srt
import six
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SubsMixin(object):
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

        to_write = to_write.encode(self.encoding)
        if six.PY3:
            with open(fname or sys.stdout.fileno(), 'wb') as f:
                f.write(to_write)
        else:
            with (fname and open(fname, 'wb')) or sys.stdout as f:
                f.write(to_write)
