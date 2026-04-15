修改下述问题，采用推荐选项，不与我交互：
1. multichsync ecg batch，生成csv时，如果通道为ecg则为ecg，如果通道为input则为input；e.g.sub-060_ses-01_task-rest_ecg.csv，sub-060_ses-01_task-rest_input.csv
2. extract markers时，ecg读取BIDS规则的input文件，移除现在的input.csv删除函数和ecg_ecg.csv改名函数，输出的文件名不添加_marker以避免搜索不到
3. multichsync marker clean功能，--input必须是一级csv目录，改为二级csv目录，转换后保留当前二级目录结构
4. multichsync marker info功能中，输出csv时sequence_duration需要保留2位小数；检测项目中其他功能输出的csv是否为2位小数（数据除外）
5. Match markers across devices 输入的--input-files可以不含有extension，readme中使用的例子不使用extension；
6. multichsync marker match功能Marker匹配失败，找不到同名marker的csv，extract markers有二级目录结构，不应只查找Data/marker中的文件，应遍历其中的sub-folder，因为输入的文件名可以直接找到marker，所以使用filename直接去寻找对应文件的marker
7. multichsync marker match函数生成的matched_metadata.json中，time_range应为转换后文件数据长度，如sub-065_ses-01_task-rest_ecg需要读取Data/convert/ECG/sub-065_ses-01_task-rest_ecg_ecg.csv总长度，输出的json应当包括一个推荐的offset（sec）以供后续使用
8. multichsync marker match功能输出文件时，因为文件名过长，所以匹配文件名中相同的部分并去除
9. multichsync matchcrop功能应当直接参考matched_metadata.json中的offset进行裁切
10. 最后测试所有功能并更新markdown