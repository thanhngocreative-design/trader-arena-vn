"""Daily current-membership check; never infer historical effective dates."""
from datetime import datetime
import hashlib,json
from value_investing import ROOT,VN,read,write
from paper_replay import completed_date

CHECKS=ROOT/'state/vn30_membership_checks'


def verify_current(cfg,end,*,now=None,fetch=None):
    if end<=cfg['verified_through']:return cfg['verified_through']
    expected=set([r for r in cfg['months'] if r['effective']<=end][-1]['members'])
    path=CHECKS/(end+'.json')
    if path.exists():
        saved=read(path)
        if saved['session']!=end or set(saved['members'])!=expected:raise ValueError('Frozen VN30 daily check differs from verified membership')
        return end
    now=now or datetime.now(VN)
    if completed_date(now)!=end:raise ValueError('Current constituents cannot verify a missing historical VN30 session')
    if fetch is None:
        from vn_market_data.sources.vietcap import VietcapSource
        fetch=lambda:VietcapSource().get_index_constituents('VN30')
    members=fetch()
    if len(members)!=30 or len(set(members))!=30:raise ValueError('Invalid current VN30 source')
    if set(members)!=expected:
        raise ValueError('VN30 changed: verify the official notice and its effective date before replaying; do not apply current members to history')
    source=json.dumps(members,separators=(',',':')).encode()
    write(path,dict(session=end,observed_at=now.isoformat(),members=members,
        source='Vietcap current getByGroup VN30',sha256=hashlib.sha256(source).hexdigest(),
        policy='Checks that the current provider list still matches the last verified effective notice; a change blocks replay until official effective-date verification.'))
    return end
