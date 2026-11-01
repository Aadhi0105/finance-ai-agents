"""Pure, closed presentation registry; no engine, filesystem or provider access."""
from . import close, close_context, events, event_context, monitoring, monitoring_context, news, news_context, news_recovery, research, research_context
from .common import Builder
from .sources import adapter_for, check_source

BUILDERS = {'research': research.build, 'monitoring': monitoring.build,
            'events': events.build, 'news': news.build, 'close': close.build}


def build_view(run, source, series, artifacts):
    check_source(run, source)
    builder = Builder(run, source, series, artifacts, adapter_for(run)[2])
    BUILDERS[run.workflow](builder)
    if run.workflow == 'close' and adapter_for(run)[1] == '1.1.0':
        close_context.extend(builder)
    if run.workflow == 'monitoring' and adapter_for(run)[1] == '1.1.0':
        monitoring_context.extend(builder)
    if run.workflow == 'research' and adapter_for(run)[1] == '1.1.0':
        research_context.extend(builder)
    if run.workflow == 'events' and adapter_for(run)[1] == '1.1.0':
        event_context.extend(builder)
    if run.workflow == 'news' and adapter_for(run)[1] == '1.1.0':
        news_context.extend(builder)
    if run.workflow == 'news' and adapter_for(run)[1] == '1.2.0':
        news_recovery.extend(builder)
    return builder.finish()
