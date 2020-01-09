import re


class Parse:
    def __init__(self, abs_url, m3u_string):
        self.abs_url = abs_url
        self.playlist = m3u_string.split('\n')
        self.attribute_patt1 = r'([A-Z-]+?)=([^,"]+)'
        self.attribute_patt2 = r'([A-Z-]+?)="(.+?)"'
        # self.cache_tag = ''
        # self.key_tag = {}  # This tag is needed when the video stream is encrypted

        stream_inf_index = []
        extinf_index = []
        for line in range(len(self.playlist)):
            if re.match('#EXT-X-STREAM-INF', self.playlist[line]):
                stream_inf_index.append(line)
            elif re.match('#EXTINF', self.playlist[line]):
                extinf_index.append(line)
            # elif re.match('#EXT-X-ALLOW-CACHE', self.playlist[line]):
            #     value = re.search(r'.*:(.*)', self.playlist[line]).group(1)
            #     self.cache_tag = value.strip()
        stream_inf_index.append(len(self.playlist))
        extinf_index.append(len(self.playlist))

        self.stream_inf_tag = [self.playlist[stream_inf_index[i]: stream_inf_index[i+1]]
                               for i in range(len(stream_inf_index)-1)]
        self.extinf_tag = [self.playlist[extinf_index[i]: extinf_index[i+1]] for i in range(len(extinf_index)-1)]

    def stream_inf(self):
        for block in self.stream_inf_tag:
            attr_pairs, target_url = [], ''
            for line in range(len(block)):
                if re.match('#EXT-X-STREAM-INF', block[line]):
                    attr_pairs = re.findall(self.attribute_patt1, block[line])
                    attr_pairs += re.findall(self.attribute_patt2, block[line])
                elif not re.match('#EXT', block[line]) and block[line]:
                    target_url = self.get_true_url(block[line])

            attr_dict = dict(attr_pairs)
            attr_dict['url'] = target_url
            self.stream_inf_tag[self.stream_inf_tag.index(block)] = attr_dict

        return self.stream_inf_tag

    def slice_url(self):
        duration, target_url, length = 0.0, '', ''
        discontinuity_ls = []
        for block in self.extinf_tag:
            for line in range(len(block)):
                if re.match('#EXT-X-DISCONTINUITY', block[line]):
                    discontinuity_ls.append(self.extinf_tag.index(block)+1)
                if re.match('#EXTINF', block[line]):
                    value = re.search(r'.*:(.*),', block[line]).group(1)
                    duration += float(value.strip())
                if re.match('#EXT-X-BYTERANGE', block[line]):
                    length = re.search(r'.*:(\d+)[@,.]\d*', block[line]).group(1)
                elif not re.match('#EXT', block[line]) and block[line]:
                    target_url = self.get_true_url(block[line])
            self.extinf_tag[self.extinf_tag.index(block)] = {'url': target_url, 'length': length}

        # skip discontinuous slice
        for ind in range(len(discontinuity_ls) // 2):
            del self.extinf_tag[discontinuity_ls[ind*2]: discontinuity_ls[ind*2+1]]

        return self.extinf_tag, duration

    def get_true_url(self, old_url):
        locator_ls1 = self.abs_url.strip('/').split('/')
        locator_ls2 = old_url.strip('/').split('/')
        for ind, block in enumerate(locator_ls1):
            if block == locator_ls2[0] and locator_ls1[ind:] == locator_ls2[: len(locator_ls1) - ind]:
                return '/'.join(locator_ls1[: ind] + locator_ls2)
        return '/'.join(locator_ls1 + locator_ls2)
