// Package limiter: 滑窗限流 + 死 key GC（平移 Python 修复版）
package limiter

import (
	"container/list"
	"sync"
	"time"
)

type Limiter struct {
	rpm   int
	mu    sync.Mutex
	hits  map[string]*list.List
	gcCnt int
}

func New(rpm int) *Limiter {
	return &Limiter{rpm: rpm, hits: make(map[string]*list.List)}
}

func (l *Limiter) Allow(key string, rpm int) (bool, int) {
	if rpm <= 0 {
		rpm = l.rpm
	}
	now := time.Now()
	l.mu.Lock()
	defer l.mu.Unlock()
	l.gcCnt++
	if l.gcCnt > 1000 {
		l.gcCnt = 0
		for k, q := range l.hits {
			if q.Len() == 0 {
				delete(l.hits, k)
			}
		}
	}
	q, ok := l.hits[key]
	if !ok {
		q = list.New()
		l.hits[key] = q
	}
	for q.Len() > 0 {
		t := q.Front().Value.(time.Time)
		if now.Sub(t) > 60*time.Second {
			q.Remove(q.Front())
		} else {
			break
		}
	}
	if q.Len() >= rpm {
		oldest := q.Front().Value.(time.Time)
		retry := int(60 - now.Sub(oldest).Seconds()) + 1
		return false, retry
	}
	q.PushBack(now)
	return true, 0
}
