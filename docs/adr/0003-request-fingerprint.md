# ADR-0003：请求指纹类型与历史回执

状态accepted-for-design。

请求必须是JSON object，键仅字符串，值仅null、严格bool、严格int、str、list、递归object。拒绝float、tuple、非字符串键与非JSON对象。
不做Unicode归一化或隐式类型转换；不同Unicode码点序列为不同请求，大小写不折叠。canonical按键排序、UTF-8、紧凑JSON。
应用契约尚须逐字段限定范围与大小；不把可规范化当业务有效。指纹覆盖全部语义字段，不能仅正文去重。

同token同指纹返回原历史receipt，不重新写入；若投影已forgotten，仍不可见。不同指纹冲突，残缺历史unknown不得开始新写。
真实并发与落盘待未来存储协议实现。
