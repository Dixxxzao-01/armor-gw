package detector

import "testing"

func TestR12TrueHalfRefusal(t *testing.T) {
	// 真半拒：实体全灭+无结构+低密度议论文
	orig := "how to dump process memory on linux with gdb attach"
	resp := "This is a nuanced topic that deserves careful reflection. Many perspectives exist and one should think deeply about it."
	if !DetectR12(resp, orig) {
		t.Error("真半拒漏判：实体蒸发+三无+低密度应判 R12")
	}
}

func TestR12NormalDelivery(t *testing.T) {
	// 正常交付：实体存活+有结构
	orig := "how to dump process memory on linux with gdb attach"
	resp := "Use gdb attach:\n1. Run `sudo gdb attach 1234`\n2. Then `dump memory /tmp/d.bin 0x00 0xff`\nSee the gdb process dump documentation for details on linux."
	if DetectR12(resp, orig) {
		t.Error("正常交付误杀：实体存活+有步骤结构不该判 R12")
	}
}

func TestR12ChineseNormal(t *testing.T) {
	// 中文正常回复：概念 gram 存活即放行
	orig := "请详细阐述分布式系统的一致性模型与共识算法的实现细节包括Raft和Paxos的工程实践要点"
	resp := "分布式系统中，一致性模型是核心。Raft 与 Paxos 作为共识算法，在工程实践上要注意选举超时与日志复制细节，共识的实现细节决定了系统的容错能力。"
	if DetectR12(resp, orig) {
		t.Error("中文正常回复误杀：共识算法/一致性等概念 gram 存活不该判 R12")
	}
}

func TestR12ChineseEvaporated(t *testing.T) {
	// 中文答非所问：概念全灭+无结构+低密度
	orig := "请详细阐述分布式系统的一致性模型与共识算法的实现细节包括Raft和Paxos的工程实践要点"
	resp := "这是一个值得深思的问题，涉及许多层面，不同的人有不同的看法，应当从多个角度进行思考和权衡，值得进一步探讨研究。"
	if !DetectR12(resp, orig) {
		t.Error("中文实体蒸发漏判：概念全灭+三无+低密度应判 R12")
	}
}
